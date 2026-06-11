"""Deterministic saving goal planning and persistence helpers."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any
from uuid import uuid4

LIMITATION = (
    "Kế hoạch này dựa trên dữ liệu hiện có và là ước tính quản lý ngân sách, "
    "không phải tư vấn tài chính chuyên nghiệp hay khuyến nghị đầu tư."
)

FLEXIBLE_CATEGORIES = {"an uong", "mua sam", "giai tri", "subscriptions", "ca phe", "dat do an", "dich vu"}
ESSENTIAL_CATEGORIES = {"nha", "tien nha", "suc khoe", "tra no", "giao duc", "dien nuoc"}


def plan_savings_goal(
    user_id: str,
    *,
    name: str,
    target_amount: float,
    current_amount: float = 0,
    target_date: str,
    currency: str = "VND",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del user_id
    clean_name = str(name or "").strip()
    target = _positive_amount(target_amount, "target_amount")
    current = _non_negative_amount(current_amount, "current_amount")
    target_day = _parse_future_date(target_date)
    today = date.today()
    currency = _currency(currency)
    months = _months_between(today, target_day)
    if months <= 0:
        raise ValueError("target_date must leave at least one month to save")

    remaining = max(target - current, 0)
    required_monthly = remaining / months if months else remaining
    required_weekly = required_monthly / 4
    required_daily = required_monthly / 30
    context = context or {}
    income = _as_float(context.get("average_monthly_income") or context.get("total_income"))
    expense = _as_float(context.get("average_monthly_expense") or context.get("total_spent"))
    available = _as_float(context.get("available_monthly_cashflow"))
    if not available and (income or expense):
        available = income - expense

    label, confidence, reason = _feasibility(remaining, required_monthly, available, income)
    monthly_gap = available - required_monthly
    by_category = context.get("by_category") or {}
    return {
        "goal": {
            "name": clean_name or f"Tiết kiệm {target:,.0f} {currency}",
            "target_amount": round(target, 2),
            "current_amount": round(current, 2),
            "remaining_amount": round(remaining, 2),
            "currency": currency,
            "start_date": today.isoformat(),
            "target_date": target_day.isoformat(),
            "months_remaining": months,
        },
        "required_plan": {
            "required_monthly_saving": round(required_monthly, 2),
            "required_weekly_saving": round(required_weekly, 2),
            "required_daily_saving": round(required_daily, 2),
        },
        "current_capacity": {
            "average_monthly_income": round(income, 2),
            "average_monthly_expense": round(expense, 2),
            "available_monthly_cashflow": round(available, 2),
            "forecasted_end_balance": _round_or_none(context.get("forecasted_end_balance")),
            "financial_health_score": context.get("financial_health_score"),
        },
        "feasibility": {
            "label": label,
            "monthly_gap": round(monthly_gap, 2),
            "feasibility_ratio": round((available / required_monthly), 4) if required_monthly > 0 else None,
            "confidence": confidence,
            "reason": reason,
        },
        "recommended_adjustments": _recommended_adjustments(by_category, required_monthly, available),
        "risks": _risks(label, monthly_gap),
        "next_actions": _next_actions(required_monthly, currency, label),
        "missing_data": _missing_data(income, expense),
        "limitations": [LIMITATION],
    }


def simulate_savings_adjustment(
    user_id: str,
    *,
    target_amount: float,
    current_amount: float,
    target_date: str,
    adjustments: list[dict[str, Any]],
    currency: str = "VND",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = plan_savings_goal(
        user_id,
        name="Mô phỏng mục tiêu tiết kiệm",
        target_amount=target_amount,
        current_amount=current_amount,
        target_date=target_date,
        currency=currency,
        context=context,
    )
    extra_cashflow = sum(max(_as_float(item.get("monthly_reduction")), 0) for item in adjustments or [])
    adjusted_context = dict(context or {})
    adjusted_context["available_monthly_cashflow"] = (
        _as_float(base["current_capacity"]["available_monthly_cashflow"]) + extra_cashflow
    )
    adjusted = plan_savings_goal(
        user_id,
        name=base["goal"]["name"],
        target_amount=target_amount,
        current_amount=current_amount,
        target_date=target_date,
        currency=currency,
        context=adjusted_context,
    )
    return {
        "base_plan": base,
        "adjusted_plan": adjusted,
        "adjustments": [
            {
                "category": str(item.get("category") or ""),
                "monthly_reduction": round(max(_as_float(item.get("monthly_reduction")), 0), 2),
            }
            for item in adjustments or []
        ],
        "impact": {
            "additional_monthly_cashflow": round(extra_cashflow, 2),
            "monthly_gap_before": base["feasibility"]["monthly_gap"],
            "monthly_gap_after": adjusted["feasibility"]["monthly_gap"],
            "label_before": base["feasibility"]["label"],
            "label_after": adjusted["feasibility"]["label"],
        },
        "limitations": [LIMITATION],
    }


def get_savings_goals(user_id: str, *, status: str = "active") -> dict[str, Any]:
    from spectra.web import server

    status = _status(status, allow_all=True)
    where = ["user_id = ?"]
    params: list[Any] = [user_id]
    if status != "all":
        where.append("status = ?")
        params.append(status)
    with server._get_db() as db:
        rows = db._conn.execute(
            f"""
            SELECT id, name, target_amount, current_amount, currency, start_date, target_date,
                   monthly_required_amount, status, priority, created_at, updated_at
            FROM app_savings_goals
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC
            """,
            params,
        ).fetchall()
    return {"goals": [_goal_row(row) for row in rows], "status": status, "total": len(rows)}


def create_savings_goal(user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from spectra.web import server

    plan = plan_savings_goal(
        user_id,
        name=str(payload.get("name") or ""),
        target_amount=_as_float(payload.get("target_amount")),
        current_amount=_as_float(payload.get("current_amount")),
        target_date=str(payload.get("target_date") or ""),
        currency=str(payload.get("currency") or "VND"),
        context=payload.get("context") if isinstance(payload.get("context"), dict) else None,
    )
    goal_id = f"goal_{uuid4().hex[:12]}"
    goal = plan["goal"]
    with server._get_db() as db:
        db._conn.execute(
            """
            INSERT INTO app_savings_goals (
                id, user_id, name, target_amount, current_amount, currency,
                start_date, target_date, monthly_required_amount, status, priority, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, 'chatbot')
            """,
            (
                goal_id,
                user_id,
                goal["name"],
                goal["target_amount"],
                goal["current_amount"],
                goal["currency"],
                goal["start_date"],
                goal["target_date"],
                plan["required_plan"]["required_monthly_saving"],
                str(payload.get("priority") or "medium"),
            ),
        )
        db._conn.commit()
    return {"ok": True, "goal": {**goal, "id": goal_id, "status": "active"}, "plan": plan}


def update_savings_goal(user_id: str, goal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    from spectra.web import server

    safe_id = str(goal_id or "").strip()
    if not safe_id:
        raise ValueError("goal_id is required")
    allowed = {"name", "target_amount", "current_amount", "target_date", "status", "priority"}
    updates = {key: value for key, value in payload.items() if key in allowed and value is not None}
    if "status" in updates:
        updates["status"] = _status(str(updates["status"]))
    if not updates:
        raise ValueError("No supported fields to update")
    with server._get_db() as db:
        existing = db._conn.execute("SELECT id FROM app_savings_goals WHERE id = ? AND user_id = ?", (safe_id, user_id)).fetchone()
        if not existing:
            raise ValueError("Goal not found")
        assignments = ", ".join(f"{key} = ?" for key in updates)
        db._conn.execute(
            f"UPDATE app_savings_goals SET {assignments}, updated_at = now() WHERE id = ? AND user_id = ?",
            [*updates.values(), safe_id, user_id],
        )
        db._conn.commit()
    return {"ok": True, "goal_id": safe_id, "updated": sorted(updates)}


def archive_savings_goal(user_id: str, goal_id: str) -> dict[str, Any]:
    from spectra.web import server

    safe_id = str(goal_id or "").strip()
    if not safe_id:
        raise ValueError("goal_id is required")
    with server._get_db() as db:
        cur = db._conn.execute(
            """
            UPDATE app_savings_goals
            SET status = 'archived', archived_at = now(), updated_at = now()
            WHERE id = ? AND user_id = ?
            """,
            (safe_id, user_id),
        )
        db._conn.commit()
    if cur.rowcount <= 0:
        raise ValueError("Goal not found")
    return {"ok": True, "goal_id": safe_id, "status": "archived"}


def extract_goal_from_message(message: str) -> dict[str, Any] | None:
    folded = _fold(message)
    amount = _extract_amount(folded)
    months = _extract_months(folded)
    if not amount or not months:
        return None
    today = date.today()
    target_day = _add_months(today, months)
    return {
        "name": f"Tiết kiệm {amount:,.0f} VND trong {months} tháng",
        "target_amount": amount,
        "current_amount": 0,
        "target_date": target_day.isoformat(),
        "currency": "VND",
    }


def _feasibility(remaining: float, required: float, available: float, income: float) -> tuple[str, str, str]:
    if remaining <= 0:
        return "achieved", "high", "Mục tiêu đã đạt được với số tiền hiện tại."
    if income <= 0 and available <= 0:
        return "insufficient_data", "low", "Chưa có đủ dữ liệu thu nhập/dòng tiền để đánh giá chắc chắn."
    if required <= available * 0.5:
        return "realistic", "high", "Mục tiêu có biên an toàn tốt so với dòng tiền hiện tại."
    if required <= available * 0.8:
        return "challenging", "medium", "Mục tiêu khá khó nhưng có thể đạt nếu giữ kỷ luật chi tiêu."
    if required <= available:
        return "risky", "medium", "Mục tiêu sát với dòng tiền dư, biên an toàn không lớn."
    return "unrealistic", "medium" if income > 0 else "low", "Dòng tiền hiện tại chưa đủ để đạt mục tiêu đúng hạn."


def _recommended_adjustments(by_category: dict[str, Any], required: float, available: float) -> list[dict[str, Any]]:
    gap = max(required - available, 0)
    items = []
    for category, amount in sorted(by_category.items(), key=lambda item: -abs(_as_float(item[1]))):
        folded = _fold(str(category))
        if folded in ESSENTIAL_CATEGORIES:
            continue
        if folded not in FLEXIBLE_CATEGORIES and len(items) >= 1:
            continue
        monthly = abs(_as_float(amount))
        suggested = min(max(gap / 2, monthly * 0.1, 100_000), monthly * 0.25) if monthly else 0
        if suggested <= 0:
            continue
        items.append(
            {
                "category": str(category),
                "current_monthly_spend": round(monthly, 2),
                "suggested_reduction": round(suggested, 2),
                "difficulty": "medium" if suggested <= monthly * 0.15 else "hard",
                "reason": "Đây là nhóm chi có thể tối ưu từng bước.",
            }
        )
        if len(items) >= 3:
            break
    return items


def _risks(label: str, monthly_gap: float) -> list[str]:
    risks = []
    if label in {"risky", "unrealistic"}:
        risks.append("Nếu phát sinh khoản chi lớn, mục tiêu có thể bị chậm.")
    if monthly_gap < 0:
        risks.append("Dòng tiền hiện tại thiếu so với mức cần tiết kiệm mỗi tháng.")
    return risks


def _next_actions(required_monthly: float, currency: str, label: str) -> list[str]:
    actions = [f"Đặt mục tiêu tiết kiệm khoảng {required_monthly:,.0f} {currency}/tháng."]
    if label in {"challenging", "risky", "unrealistic"}:
        actions.append("Theo dõi các nhóm chi linh hoạt mỗi tuần.")
    actions.append("Kiểm tra tiến độ sau 30 ngày.")
    return actions[:3]


def _goal_row(row: tuple[Any, ...]) -> dict[str, Any]:
    goal_id, name, target, current, currency, start, target_date, monthly, status, priority, created, updated = row
    return {
        "id": str(goal_id),
        "name": str(name),
        "target_amount": _as_float(target),
        "current_amount": _as_float(current),
        "remaining_amount": max(_as_float(target) - _as_float(current), 0),
        "currency": str(currency),
        "start_date": str(start)[:10],
        "target_date": str(target_date)[:10],
        "monthly_required_amount": _as_float(monthly),
        "status": str(status),
        "priority": str(priority),
        "created_at": str(created),
        "updated_at": str(updated),
    }


def _extract_amount(text: str) -> float | None:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(trieu|triệu|m|k|nghin|ngan)?", text)
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = match.group(2) or ""
    if unit in {"trieu", "triệu", "m"}:
        return number * 1_000_000
    if unit in {"k", "nghin", "ngan"}:
        return number * 1_000
    return number


def _extract_months(text: str) -> int | None:
    match = re.search(r"(\d{1,2})\s*thang", text)
    return int(match.group(1)) if match else None


def _parse_future_date(value: str) -> date:
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("target_date must be YYYY-MM-DD") from exc
    if parsed <= date.today():
        raise ValueError("target_date must be in the future")
    return parsed


def _months_between(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day > start.day:
        months += 1
    return max(months, 0)


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, 28)
    return date(year, month, day)


def _status(value: str, *, allow_all: bool = False) -> str:
    allowed = {"active", "completed", "paused", "archived"}
    if allow_all:
        allowed.add("all")
    normalized = str(value or "active").strip().lower()
    if normalized not in allowed:
        return "active"
    return normalized


def _currency(value: str) -> str:
    normalized = str(value or "VND").strip().upper()
    return normalized if re.match(r"^[A-Z]{3}$", normalized) else "VND"


def _positive_amount(value: Any, name: str) -> float:
    amount = _as_float(value)
    if amount <= 0:
        raise ValueError(f"{name} must be positive")
    return amount


def _non_negative_amount(value: Any, name: str) -> float:
    amount = _as_float(value)
    if amount < 0:
        raise ValueError(f"{name} must be non-negative")
    return amount


def _missing_data(income: float, expense: float) -> list[str]:
    missing = []
    if income <= 0:
        missing.append("income")
    if expense <= 0:
        missing.append("spending")
    return missing


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round_or_none(value: Any) -> float | None:
    return None if value is None else round(_as_float(value), 2)


def _fold(value: str) -> str:
    value = str(value or "").replace("đ", "d").replace("Đ", "D")
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.lower().split())
