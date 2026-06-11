"""Deterministic read-only insight helpers for chatbot finance questions."""

from __future__ import annotations

import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Any

LIMITATION = "Day la phan tich uoc tinh dua tren du lieu giao dich hien co, khong phai tu van tai chinh chuyen nghiep."
DEBT_LIMITATION = (
    "Day chi la cac khoan thanh toan co dau hieu lien quan den no/tra gop; he thong chua co du lieu du no con lai."
)
CASHFLOW_LIMITATION = "Lich dong tien la uoc tinh tu giao dich dinh ky va toc do chi tieu gan day."

ESSENTIAL_CATEGORIES = {
    "nha o",
    "nha cua",
    "tien thue nha",
    "hoa don",
    "dien nuoc",
    "suc khoe",
    "bao hiem",
    "giao duc",
    "tra no",
}
DEBT_PATTERNS = [
    "tra no",
    "tra gop",
    "installment",
    "loan",
    "credit card",
    "the tin dung",
    "vay",
    "mortgage",
]


def get_recurring_transactions(user_id: str, *, scope: str = "cycle", limit: int = 10) -> dict[str, Any]:
    rows = _transaction_rows(user_id)
    period = _period_for_scope(scope)
    safe_limit = _clamp_int(limit, default=10, minimum=1, maximum=20)
    items = _recurring_items(rows, period=period)
    limited = items[:safe_limit]
    monthly_total = sum(_as_float(item.get("monthly_estimate")) for item in items if item.get("kind") != "income")
    income_total = sum(_as_float(item.get("monthly_estimate")) for item in items if item.get("kind") == "income")
    price_changes = [item for item in items if item.get("price_change_direction")]
    return {
        "scope": _scope(scope),
        "period": _period_payload(period),
        "items": limited,
        "summary": {
            "active_count": len(items),
            "monthly_estimate": round(monthly_total, 2),
            "recurring_income_estimate": round(income_total, 2),
            "annual_projection": round(monthly_total * 12, 2),
            "price_change_count": len(price_changes),
        },
        "price_changes": price_changes[:5],
        "limitations": [] if items else ["Khong tim thay khoan dinh ky nao tu du lieu hien co.", LIMITATION],
    }


def compare_period_spending(
    user_id: str,
    *,
    period_a_from: str = "",
    period_a_to: str = "",
    period_b_from: str = "",
    period_b_to: str = "",
) -> dict[str, Any]:
    period_a, period_b = _comparison_periods(period_a_from, period_a_to, period_b_from, period_b_to)
    # Fetch once from app history to support user scoping in one place.
    rows = _transaction_rows_for_periods(user_id, period_a, period_b)
    a = _aggregate_period(rows, period_a)
    b = _aggregate_period(rows, period_b)
    return {
        "period_a": {**_period_payload(period_a), "label": "current"},
        "period_b": {**_period_payload(period_b), "label": "previous"},
        "totals": {
            "period_a_spent": a["total_spent"],
            "period_b_spent": b["total_spent"],
            "spent_delta": round(a["total_spent"] - b["total_spent"], 2),
            "spent_delta_pct": _pct_delta(a["total_spent"], b["total_spent"]),
            "period_a_income": a["total_income"],
            "period_b_income": b["total_income"],
            "income_delta": round(a["total_income"] - b["total_income"], 2),
            "transaction_count_delta": a["transaction_count"] - b["transaction_count"],
        },
        "category_deltas": _deltas(a["by_category"], b["by_category"], key_name="category"),
        "merchant_deltas": _deltas(a["by_merchant"], b["by_merchant"], key_name="merchant"),
        "limitations": [LIMITATION] if not a["transaction_count"] and not b["transaction_count"] else [],
    }


def explain_budget_overrun(
    user_id: str,
    *,
    scope: str = "cycle",
    category: str = "",
    summary_payload: dict[str, Any] | None = None,
    budget_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del summary_payload
    period = _period_for_scope(scope)
    target = _fold(category)
    budget_items = list((budget_payload or {}).get("items") or [])
    candidates = []
    for item in budget_items:
        status = str(item.get("status") or "")
        cat = str(item.get("category") or "")
        if target and _fold(cat) != target:
            continue
        spent = _as_float(item.get("spent"))
        limit = _as_float(item.get("limit"))
        projected = _as_float(item.get("projected") or item.get("projected_spend") or spent)
        if status in {"red", "yellow", "over", "at_risk"} or (limit > 0 and (spent >= limit or projected > limit)):
            candidates.append(
                {
                    "category": cat,
                    "actual_spend": round(spent, 2),
                    "budget_limit": round(limit, 2),
                    "projected_spend": round(projected, 2),
                    "over_amount": round(max(spent - limit, 0), 2) if limit > 0 else 0,
                    "projected_over_amount": round(max(projected - limit, 0), 2) if limit > 0 else 0,
                    "status": status or ("over" if spent >= limit > 0 else "at_risk"),
                }
            )
    rows = _transaction_rows_for_period(user_id, period)
    for candidate in candidates:
        cat_fold = _fold(candidate["category"])
        drivers = [
            {
                "date": row["date"].isoformat(),
                "merchant": row["merchant"],
                "amount": round(abs(row["amount"]), 2),
                "category": row["category"],
            }
            for row in rows
            if row["amount"] < 0 and _fold(row["category"]) == cat_fold
        ]
        drivers.sort(key=lambda item: item["amount"], reverse=True)
        candidate["top_drivers"] = drivers[:5]
        candidate["suggested_reduction"] = round(max(candidate["projected_over_amount"], candidate["over_amount"]), 2)
    return {
        "scope": _scope(scope),
        "period": _period_payload(period),
        "categories": candidates[:5],
        "summary": {
            "over_or_at_risk_count": len(candidates),
            "total_projected_over_amount": round(sum(_as_float(item["projected_over_amount"]) for item in candidates), 2),
        },
        "limitations": [] if candidates else ["Khong thay danh muc nao vuot hoac co nguy co vuot ngan sach trong du lieu hien co."],
    }


def get_cashflow_calendar(user_id: str, *, days: int = 30, forecast_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    safe_days = _clamp_int(days, default=30, minimum=7, maximum=45)
    today = date.today()
    forecast = forecast_payload or {}
    current_balance = _as_float(forecast.get("current_balance"))
    avg_daily = _as_float(forecast.get("avg_daily_spending"))
    rows = _transaction_rows(user_id)
    upcoming = _upcoming_recurring(rows, today=today, days=safe_days)
    checkpoints = []
    risk_days = []
    balance = current_balance
    events_by_date: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for event in upcoming:
        events_by_date[date.fromisoformat(event["estimated_date"])].append(event)
    for offset in range(safe_days + 1):
        day = today + timedelta(days=offset)
        if offset > 0:
            balance -= avg_daily
        for event in events_by_date.get(day, []):
            balance += _as_float(event["amount"])
        point = {
            "date": day.isoformat(),
            "estimated_balance": round(balance, 2),
            "events": events_by_date.get(day, []),
        }
        checkpoints.append(point)
        if balance < 0:
            risk_days.append(point)
    return {
        "days": safe_days,
        "current_balance": round(current_balance, 2),
        "avg_daily_spending": round(avg_daily, 2),
        "checkpoints": checkpoints,
        "upcoming_events": upcoming[:20],
        "risk_days": risk_days[:10],
        "limitations": [CASHFLOW_LIMITATION],
    }


def simulate_purchase_impact(
    user_id: str,
    *,
    amount: float,
    category: str = "",
    purchase_date: str = "",
    scope: str = "cycle",
    summary_payload: dict[str, Any] | None = None,
    budget_payload: dict[str, Any] | None = None,
    forecast_payload: dict[str, Any] | None = None,
    goals_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del user_id
    safe_amount = max(_as_float(amount), 0)
    purchase_day = _parse_date_or_today(purchase_date)
    cat = str(category or "").strip()
    summary = summary_payload or {}
    budget = budget_payload or {}
    forecast = forecast_payload or {}
    goals = list((goals_payload or {}).get("goals") or [])
    total_spent_after = _as_float(summary.get("total_spent")) + safe_amount
    predicted_after = _as_float(forecast.get("predicted_end_of_month_balance")) - safe_amount
    budget_item = _find_budget_item(budget, cat)
    remaining_before = _as_float(budget_item.get("limit")) - _as_float(budget_item.get("spent")) if budget_item else None
    remaining_after = remaining_before - safe_amount if remaining_before is not None else None
    goal_monthly = max((_as_float(goal.get("monthly_required_amount")) for goal in goals), default=0)
    label = _purchase_label(safe_amount, predicted_after, remaining_after, goal_monthly)
    return {
        "scope": _scope(scope),
        "purchase": {
            "amount": round(safe_amount, 2),
            "category": cat,
            "purchase_date": purchase_day.isoformat(),
        },
        "impact": {
            "total_spent_after": round(total_spent_after, 2),
            "budget_remaining_before": round(remaining_before, 2) if remaining_before is not None else None,
            "budget_remaining_after": round(remaining_after, 2) if remaining_after is not None else None,
            "predicted_end_balance_before": _round_or_none(forecast.get("predicted_end_of_month_balance")),
            "predicted_end_balance_after": round(predicted_after, 2),
            "active_goal_monthly_requirement": round(goal_monthly, 2),
        },
        "recommendation": {
            "label": label,
            "reason": _purchase_reason(label),
        },
        "limitations": [LIMITATION, "Mo phong khong ghi nhan giao dich moi."],
    }


def get_debt_summary(user_id: str, *, scope: str = "cycle") -> dict[str, Any]:
    period = _period_for_scope(scope)
    rows = [row for row in _transaction_rows_for_period(user_id, period) if row["amount"] < 0 and _is_debt_like(row)]
    merchant_totals: Counter[str] = Counter()
    for row in rows:
        merchant_totals[row["merchant"]] += abs(row["amount"])
    items = [
        {
            "merchant": merchant,
            "paid_amount": round(amount, 2),
            "payments_count": sum(1 for row in rows if row["merchant"] == merchant),
        }
        for merchant, amount in merchant_totals.most_common(10)
    ]
    monthly_estimate = sum(item["paid_amount"] for item in items)
    return {
        "scope": _scope(scope),
        "period": _period_payload(period),
        "outstanding_balance_available": False,
        "summary": {
            "debt_like_payment_count": len(rows),
            "debt_like_paid_amount": round(sum(abs(row["amount"]) for row in rows), 2),
            "monthly_payment_estimate": round(monthly_estimate, 2),
        },
        "items": items,
        "limitations": [DEBT_LIMITATION] if items else ["Khong thay khoan thanh toan co dau hieu no/tra gop trong pham vi hien tai.", DEBT_LIMITATION],
    }


def get_emergency_fund_status(
    user_id: str,
    *,
    months_target: float = 3,
    forecast_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_months = min(max(_as_float(months_target) or 3.0, 1.0), 12.0)
    period = _period_for_scope("90d")
    rows = [row for row in _transaction_rows_for_period(user_id, period) if row["amount"] < 0]
    monthly_essential = _monthly_essential_spend(rows, period)
    forecast = forecast_payload or {}
    current_balance = _as_float(forecast.get("current_balance"))
    months_covered = (current_balance / monthly_essential) if monthly_essential > 0 else None
    target_amount = monthly_essential * target_months
    gap = max(target_amount - current_balance, 0)
    status = _emergency_status(months_covered, target_months)
    return {
        "months_target": target_months,
        "current_balance": round(current_balance, 2),
        "monthly_essential_spend": round(monthly_essential, 2),
        "estimated_months_covered": round(months_covered, 2) if months_covered is not None else None,
        "target_amount": round(target_amount, 2),
        "gap_amount": round(gap, 2),
        "status": status,
        "limitations": [LIMITATION, "Quy khan cap duoc uoc tinh tu so du hien tai va chi phi thiet yeu trong lich su giao dich."],
    }


def _transaction_rows(user_id: str) -> list[dict[str, Any]]:
    from spectra.web import server

    with server._get_db() as db:
        rows = db._conn.execute(
            """
            SELECT date, clean_name, amount, category, COALESCE(original_description, '')
            FROM app_tx_history
            WHERE user_id = ?
            ORDER BY date ASC
            """,
            (user_id,),
        ).fetchall()
    return [_row(item) for item in rows]


def _transaction_rows_for_period(user_id: str, period: tuple[date, date]) -> list[dict[str, Any]]:
    start, end = period
    return [row for row in _transaction_rows(user_id) if start <= row["date"] < end]


def _transaction_rows_for_periods(user_id: str, first: tuple[date, date], second: tuple[date, date]) -> list[dict[str, Any]]:
    start = min(first[0], second[0])
    end = max(first[1], second[1])
    return [row for row in _transaction_rows(user_id) if start <= row["date"] < end]


def _row(item: tuple[Any, ...]) -> dict[str, Any]:
    tx_date, merchant, amount, category, description = item
    return {
        "date": _parse_date(str(tx_date)[:10]),
        "merchant": str(merchant or ""),
        "amount": _as_float(amount),
        "category": str(category or ""),
        "description": str(description or ""),
    }


def _recurring_items(rows: list[dict[str, Any]], *, period: tuple[date, date]) -> list[dict[str, Any]]:
    from spectra.categories import RECURRING_INCOME, RECURRING_SUBSCRIPTION, SUBSCRIPTIONS
    from spectra.recurring import detect_recurring_kind

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["merchant"]].append(row)
    items = []
    for merchant, history in buckets.items():
        if len(history) < 2:
            continue
        amounts = [abs(row["amount"]) for row in history]
        signed_amounts = [row["amount"] for row in history]
        dates = [row["date"] for row in history]
        intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates)) if (dates[i] - dates[i - 1]).days > 0]
        cadence = int(round(median(intervals))) if intervals else 30
        cadence = max(cadence, 1)
        stable_amount = _stable_amount(amounts)
        temporal_match = any(6 <= interval <= 8 or 27 <= interval <= 32 or 355 <= interval <= 370 for interval in intervals)
        recurring_kind = detect_recurring_kind(merchant, history[-1]["description"], history[-1]["amount"])
        category = str(history[-1]["category"] or "")
        if not (temporal_match and stable_amount) and recurring_kind not in {RECURRING_SUBSCRIPTION, RECURRING_INCOME} and category != SUBSCRIPTIONS:
            continue
        avg_amount = sum(amounts) / len(amounts)
        monthly_estimate = avg_amount * (30.4375 / cadence)
        last_amount = amounts[-1]
        baseline = median(amounts[:-1]) if len(amounts) > 1 else last_amount
        change_amount = round(last_amount - baseline, 2)
        change_pct = round(change_amount / baseline * 100, 1) if baseline else 0.0
        direction = ""
        if len(amounts) > 2 and abs(change_amount) >= max(1.0, baseline * 0.08):
            direction = "up" if change_amount > 0 else "down"
        kind = "income" if signed_amounts[-1] > 0 or recurring_kind == RECURRING_INCOME else "payment"
        if recurring_kind == RECURRING_SUBSCRIPTION or category == SUBSCRIPTIONS:
            kind = "subscription"
        if _is_debt_like(history[-1]):
            kind = "debt_payment"
        in_period = sum(abs(row["amount"]) for row in history if period[0] <= row["date"] < period[1])
        items.append(
            {
                "merchant": merchant,
                "kind": kind,
                "category": category,
                "last_amount": round(last_amount, 2),
                "average_amount": round(avg_amount, 2),
                "cadence_days": cadence,
                "last_charge_date": dates[-1].isoformat(),
                "next_estimated_date": (dates[-1] + timedelta(days=cadence)).isoformat(),
                "monthly_estimate": round(monthly_estimate, 2),
                "annual_projection": round(monthly_estimate * 12, 2),
                "in_current_period": round(in_period, 2),
                "payments_count": len(history),
                "price_change_direction": direction,
                "change_amount": change_amount,
                "change_pct": change_pct,
            }
        )
    items.sort(key=lambda row: (_as_float(row.get("monthly_estimate"))), reverse=True)
    return items


def _upcoming_recurring(rows: list[dict[str, Any]], *, today: date, days: int) -> list[dict[str, Any]]:
    items = _recurring_items(rows, period=(today, today + timedelta(days=days)))
    events = []
    horizon = today + timedelta(days=days)
    for item in items:
        try:
            event_day = _parse_date(str(item["next_estimated_date"]))
        except ValueError:
            continue
        while event_day < today:
            event_day += timedelta(days=max(_clamp_int(item.get("cadence_days"), default=30, minimum=1, maximum=370), 1))
        if event_day > horizon:
            continue
        amount = _as_float(item.get("last_amount"))
        if item.get("kind") != "income":
            amount = -abs(amount)
        events.append(
            {
                "estimated_date": event_day.isoformat(),
                "merchant": item.get("merchant"),
                "kind": item.get("kind"),
                "amount": round(amount, 2),
            }
        )
    events.sort(key=lambda item: item["estimated_date"])
    return events


def _aggregate_period(rows: list[dict[str, Any]], period: tuple[date, date]) -> dict[str, Any]:
    by_category: Counter[str] = Counter()
    by_merchant: Counter[str] = Counter()
    total_spent = 0.0
    total_income = 0.0
    count = 0
    for row in rows:
        if not (period[0] <= row["date"] < period[1]):
            continue
        count += 1
        if row["amount"] < 0:
            amount = abs(row["amount"])
            total_spent += amount
            by_category[row["category"]] += amount
            by_merchant[row["merchant"]] += amount
        else:
            total_income += row["amount"]
    return {
        "total_spent": round(total_spent, 2),
        "total_income": round(total_income, 2),
        "transaction_count": count,
        "by_category": by_category,
        "by_merchant": by_merchant,
    }


def _deltas(current: Counter[str], previous: Counter[str], *, key_name: str) -> list[dict[str, Any]]:
    keys = set(current) | set(previous)
    rows = [
        {
            key_name: key,
            "period_a_amount": round(_as_float(current.get(key)), 2),
            "period_b_amount": round(_as_float(previous.get(key)), 2),
            "delta": round(_as_float(current.get(key)) - _as_float(previous.get(key)), 2),
            "delta_pct": _pct_delta(_as_float(current.get(key)), _as_float(previous.get(key))),
        }
        for key in keys
    ]
    rows.sort(key=lambda item: abs(_as_float(item["delta"])), reverse=True)
    return rows[:5]


def _comparison_periods(a_from: str, a_to: str, b_from: str, b_to: str) -> tuple[tuple[date, date], tuple[date, date]]:
    if a_from and a_to and b_from and b_to:
        return (_parse_date(a_from), _parse_date(a_to)), (_parse_date(b_from), _parse_date(b_to))
    today = date.today()
    current_start = today.replace(day=1)
    next_month = _add_months(current_start, 1)
    previous_start = _add_months(current_start, -1)
    return (current_start, next_month), (previous_start, current_start)


def _period_for_scope(scope: str) -> tuple[date, date]:
    normalized = _scope(scope)
    today = date.today()
    if normalized == "90d":
        return today - timedelta(days=90), today + timedelta(days=1)
    if normalized == "ytd":
        return date(today.year, 1, 1), today + timedelta(days=1)
    return today.replace(day=1), _add_months(today.replace(day=1), 1)


def _period_payload(period: tuple[date, date]) -> dict[str, str]:
    return {"start": period[0].isoformat(), "end": period[1].isoformat()}


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    return date(year, month, 1)


def _stable_amount(amounts: list[float]) -> bool:
    if len(amounts) < 2:
        return False
    baseline = median(amounts[:-1]) if len(amounts) > 2 else amounts[0]
    return abs(amounts[-1] - baseline) <= max(3.0, abs(baseline * 0.2))


def _is_debt_like(row: dict[str, Any]) -> bool:
    combined = _fold(f"{row.get('merchant', '')} {row.get('description', '')} {row.get('category', '')}")
    return any(pattern in combined for pattern in DEBT_PATTERNS)


def _monthly_essential_spend(rows: list[dict[str, Any]], period: tuple[date, date]) -> float:
    total = 0.0
    for row in rows:
        if _fold(row["category"]) in ESSENTIAL_CATEGORIES:
            total += abs(row["amount"])
    days = max((period[1] - period[0]).days, 1)
    return total / days * 30.4375


def _find_budget_item(budget: dict[str, Any], category: str) -> dict[str, Any] | None:
    target = _fold(category)
    for item in list(budget.get("items") or []):
        if target and _fold(str(item.get("category") or "")) == target:
            return dict(item)
    return None


def _purchase_label(amount: float, predicted_after: float, remaining_after: float | None, goal_monthly: float) -> str:
    if amount <= 0:
        return "safe"
    if predicted_after < 0 or (remaining_after is not None and remaining_after < 0):
        return "not_recommended"
    if predicted_after < amount * 0.5 or (goal_monthly > 0 and amount > goal_monthly):
        return "risky"
    if remaining_after is not None and remaining_after < amount * 0.5:
        return "watch"
    return "safe"


def _purchase_reason(label: str) -> str:
    return {
        "safe": "Khoan mua nay co ve van nam trong bien an toan theo du lieu hien co.",
        "watch": "Khoan mua nay co the lam ngan sach con lai mong hon, nen theo doi sat.",
        "risky": "Khoan mua nay co rui ro anh huong muc tieu tiet kiem hoac so du cuoi thang.",
        "not_recommended": "Khoan mua nay co the lam vuot ngan sach hoac am so du uoc tinh.",
    }.get(label, "Can xem them du lieu truoc khi quyet dinh.")


def _emergency_status(months_covered: float | None, target: float) -> str:
    if months_covered is None:
        return "insufficient"
    if months_covered >= target * 1.5:
        return "strong"
    if months_covered >= target:
        return "on_track"
    if months_covered >= max(target * 0.33, 1):
        return "partial"
    return "insufficient"


def _pct_delta(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _scope(value: str) -> str:
    normalized = str(value or "cycle").strip().lower()
    return normalized if normalized in {"cycle", "90d", "ytd"} else "cycle"


def _parse_date_or_today(value: str) -> date:
    if not str(value or "").strip():
        return date.today()
    return _parse_date(value)


def _parse_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _round_or_none(value: Any) -> float | None:
    return None if value is None else round(_as_float(value), 2)


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fold(value: str) -> str:
    value = str(value or "").replace("đ", "d").replace("Đ", "D").replace("Ä‘", "d").replace("Ä", "D")
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.lower().split())
