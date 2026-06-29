"""Deterministic read-only insight helpers for chatbot finance questions."""

from __future__ import annotations

import unicodedata
import zoneinfo
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any

@dataclass
class ComparisonPeriods:
    period_a_start: date
    period_a_end: date      # exclusive
    period_b_start: date
    period_b_end: date      # exclusive
    was_swapped: bool       # để log/debug
    was_aligned: bool       # period_b có bị truncate không
    limitations: list[str]  # warnings


def get_today_in_user_timezone(tz_str: str = "Asia/Ho_Chi_Minh") -> date:
    """Lấy ngày hiện tại theo timezone của user, không phải server UTC."""
    return datetime.now(zoneinfo.ZoneInfo(tz_str)).date()

LIMITATION = "Day la phan tich uoc tinh dua tren du lieu giao dich hien co, khong phai tu van tai chinh chuyen nghiep."
DEBT_LIMITATION = (
    "Day chi la cac khoan thanh toan co dau hieu lien quan den no/tra gop; he thong chua co du lieu du no con lai."
)
CASHFLOW_LIMITATION = "Lich dong tien la uoc tinh tu giao dich dinh ky va toc do chi tieu gan day."
PEER_BENCHMARK_LIMITATION = (
    "Chuan tham chieu la huong dan chung (quy tac 50/30/20 va muc ky vong theo nhom thu nhap), "
    "khong phai du lieu thuc te tu nguoi dung khac. Spectra khong thu thap du lieu nhan khau hoc."
)

# 50/30/20 baseline + muc ky vong dieu chinh theo nhom thu nhap (thu nhap thang, VND).
# Day la huong dan chung cho ho gia dinh Viet Nam, KHONG suy ra tu du lieu nguoi dung khac.
# Nhom thu nhap cao hon duoc ky vong tiet kiem ty le lon hon.
PEER_BENCHMARK_RULE = {"needs_pct": 50.0, "wants_pct": 30.0, "savings_pct": 20.0}
PEER_INCOME_BRACKETS: list[tuple[str, float, float, float, float]] = [
    # (label, nguong tren (exclusive), needs_pct, wants_pct, savings_pct)
    ("Thu nhap thap (duoi 10 trieu/thang)", 10_000_000, 60.0, 30.0, 10.0),
    ("Thu nhap trung binh thap (10-20 trieu/thang)", 20_000_000, 55.0, 30.0, 15.0),
    ("Thu nhap trung binh (20-40 trieu/thang)", 40_000_000, 50.0, 30.0, 20.0),
    ("Thu nhap kha (tren 40 trieu/thang)", float("inf"), 45.0, 30.0, 25.0),
]
PEER_BENCHMARK_TOLERANCE_PCT = 5.0

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
    comp = _comparison_periods(period_a_from, period_a_to, period_b_from, period_b_to)
    period_a = (comp.period_a_start, comp.period_a_end)
    period_b = (comp.period_b_start, comp.period_b_end)
    
    # Fetch once from app history to support user scoping in one place.
    rows = _transaction_rows_for_periods(user_id, period_a, period_b)
    a = _aggregate_period(rows, period_a)
    b = _aggregate_period(rows, period_b)
    
    # spent delta pct and label
    spent_delta_pct, spent_delta_pct_label = _pct_delta_with_label(a["total_spent"], b["total_spent"])
    # income delta pct and label
    income_delta_pct, income_delta_pct_label = _pct_delta_with_label(a["total_income"], b["total_income"])
    
    # We combine limitations
    all_limitations = list(comp.limitations)
    if not a["transaction_count"] and not b["transaction_count"]:
        all_limitations.append(LIMITATION)
        
    return {
        "period_a": {**_period_payload(period_a), "label": "current"},
        "period_b": {**_period_payload(period_b), "label": "previous"},
        "totals": {
            "period_a_spent": a["total_spent"],
            "period_b_spent": b["total_spent"],
            "spent_delta": round(a["total_spent"] - b["total_spent"], 2),
            "spent_delta_pct": spent_delta_pct,
            "spent_delta_pct_label": spent_delta_pct_label,
            "period_a_income": a["total_income"],
            "period_b_income": b["total_income"],
            "income_delta": round(a["total_income"] - b["total_income"], 2),
            "income_delta_pct": income_delta_pct,
            "income_delta_pct_label": income_delta_pct_label,
            "transaction_count_delta": a["transaction_count"] - b["transaction_count"],
        },
        "category_deltas": _deltas(a["by_category"], b["by_category"], key_name="category"),
        "merchant_deltas": _deltas(a["by_merchant"], b["by_merchant"], key_name="merchant"),
        "limitations": all_limitations,
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
    today = get_today_in_user_timezone()
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


def get_peer_benchmark(
    user_id: str,
    *,
    scope: str = "90d",
    monthly_income_override: float | None = None,
) -> dict[str, Any]:
    """So sanh co cau chi tieu cua user voi chuan tham chieu (50/30/20 + nhom thu nhap).

    Spectra khong co du lieu nguoi dung khac, nen benchmark la bang chuan tinh,
    KHONG phai du lieu peer that. Chi tieu duoc phan thanh Needs (thiet yeu) /
    Wants (mong muon) / Savings (tiet kiem = thu nhap - chi tieu).
    """
    period = _period_for_scope(scope if scope in {"cycle", "90d", "ytd"} else "90d")
    rows = _transaction_rows_for_period(user_id, period)
    days_in_period = max((period[1] - period[0]).days, 1)
    months_in_period = days_in_period / 30.4375

    total_income = sum(row["amount"] for row in rows if row["amount"] > 0)
    spend_rows = [row for row in rows if row["amount"] < 0]
    total_spent = sum(abs(row["amount"]) for row in spend_rows)
    needs_spent = sum(abs(row["amount"]) for row in spend_rows if _fold(row["category"]) in ESSENTIAL_CATEGORIES)
    wants_spent = max(total_spent - needs_spent, 0.0)

    override = _as_float(monthly_income_override)
    monthly_income = (
        override if override > 0
        else (total_income / months_in_period if months_in_period > 0 else 0.0)
    )
    monthly_needs = needs_spent / months_in_period if months_in_period > 0 else 0.0
    monthly_wants = wants_spent / months_in_period if months_in_period > 0 else 0.0
    monthly_spent = monthly_needs + monthly_wants
    monthly_savings = monthly_income - monthly_spent

    if monthly_income <= 0:
        return {
            "scope": _scope(scope),
            "period": _period_payload(period),
            "status": "insufficient_data",
            "message": "Chua du du lieu thu nhap de so sanh voi chuan tham chieu.",
            "limitations": [LIMITATION, PEER_BENCHMARK_LIMITATION],
        }

    actual = {
        "needs_pct": round(monthly_needs / monthly_income * 100, 1),
        "wants_pct": round(monthly_wants / monthly_income * 100, 1),
        "savings_pct": round(monthly_savings / monthly_income * 100, 1),
    }
    bracket = _income_bracket(monthly_income)
    benchmark = {"needs_pct": bracket[2], "wants_pct": bracket[3], "savings_pct": bracket[4]}

    comparison = {
        "needs": _benchmark_dim(actual["needs_pct"], benchmark["needs_pct"], lower_is_better=True),
        "wants": _benchmark_dim(actual["wants_pct"], benchmark["wants_pct"], lower_is_better=True),
        "savings": _benchmark_dim(actual["savings_pct"], benchmark["savings_pct"], lower_is_better=False),
    }

    return {
        "scope": _scope(scope),
        "period": _period_payload(period),
        "income_bracket": bracket[0],
        "monthly_income": round(monthly_income, 2),
        "monthly_spent": round(monthly_spent, 2),
        "monthly_savings": round(monthly_savings, 2),
        "actual_allocation": actual,
        "benchmark_allocation": benchmark,
        "rule_50_30_20": PEER_BENCHMARK_RULE,
        "comparison": comparison,
        "overall_assessment": _benchmark_overall(comparison),
        "suggestions": _benchmark_suggestions(actual, benchmark, comparison),
        "limitations": [LIMITATION, PEER_BENCHMARK_LIMITATION],
    }


def _income_bracket(monthly_income: float) -> tuple[str, float, float, float, float]:
    for bracket in PEER_INCOME_BRACKETS:
        if monthly_income < bracket[1]:
            return bracket
    return PEER_INCOME_BRACKETS[-1]


def _benchmark_dim(actual_pct: float, target_pct: float, *, lower_is_better: bool) -> dict[str, Any]:
    diff = round(actual_pct - target_pct, 1)
    if abs(diff) <= PEER_BENCHMARK_TOLERANCE_PCT:
        status = "on_track"
    elif (diff < 0) == lower_is_better:
        status = "better"
    else:
        status = "worse"
    return {"actual_pct": actual_pct, "target_pct": target_pct, "diff_pct": diff, "status": status}


def _benchmark_overall(comparison: dict[str, dict[str, Any]]) -> str:
    statuses = [dim["status"] for dim in comparison.values()]
    worse = statuses.count("worse")
    better = statuses.count("better")
    if comparison["savings"]["status"] == "worse" or worse >= 2:
        return "needs_improvement"
    if worse == 0 and better >= 1:
        return "good"
    return "on_track"


def _benchmark_suggestions(
    actual: dict[str, float],
    benchmark: dict[str, float],
    comparison: dict[str, dict[str, Any]],
) -> list[str]:
    out: list[str] = []
    if comparison["savings"]["status"] == "worse":
        gap = round(benchmark["savings_pct"] - actual["savings_pct"], 1)
        out.append(
            f"Ty le tiet kiem ({actual['savings_pct']}%) thap hon chuan ({benchmark['savings_pct']}%) "
            f"khoang {gap} diem. Hay dat khoan tiet kiem tu dong ngay dau thang."
        )
    if comparison["wants"]["status"] == "worse":
        out.append(
            f"Chi tieu mong muon ({actual['wants_pct']}%) cao hon chuan ({benchmark['wants_pct']}%). "
            f"Ra soat cac khoan giai tri, an uong ngoai, mua sam co the cat giam."
        )
    if comparison["needs"]["status"] == "worse":
        out.append(
            f"Chi phi thiet yeu ({actual['needs_pct']}%) cao hon chuan ({benchmark['needs_pct']}%). "
            f"Xem lai tien thue nha, hoa don, dich vu co the toi uu."
        )
    if not out:
        out.append("Co cau chi tieu cua ban dang bam sat chuan tham chieu. Duy tri thoi quen nay.")
    return out


def simulate_income_change(
    user_id: str,
    *,
    income_delta: float,
    scope: str = "cycle",
) -> dict[str, Any]:
    """Mô phỏng thay đổi thu nhập và tác động đến dòng tiền, tỷ lệ tiết kiệm, khả năng đạt goal."""
    from spectra.savings_goals import get_savings_goals

    period = _period_for_scope(scope)
    rows = _transaction_rows_for_period(user_id, period)
    days_in_period = max((period[1] - period[0]).days, 1)
    months_in_period = days_in_period / 30.4375

    total_income = sum(row["amount"] for row in rows if row["amount"] > 0)
    total_spent = sum(abs(row["amount"]) for row in rows if row["amount"] < 0)

    monthly_income = total_income / months_in_period if months_in_period > 0 else 0.0
    monthly_spent = total_spent / months_in_period if months_in_period > 0 else 0.0
    monthly_surplus = monthly_income - monthly_spent

    new_monthly_income = monthly_income + income_delta
    new_monthly_surplus = new_monthly_income - monthly_spent

    savings_rate_before = round(monthly_surplus / monthly_income * 100, 1) if monthly_income > 0 else None
    savings_rate_after = round(new_monthly_surplus / new_monthly_income * 100, 1) if new_monthly_income > 0 else None

    goals_data = get_savings_goals(user_id, status="active")
    active_goals = list((goals_data or {}).get("goals") or [])
    goal_monthly_required = max(
        (_as_float(g.get("monthly_required_amount") or g.get("required_monthly_saving") or 0) for g in active_goals),
        default=0.0,
    )
    goal_feasible_before = monthly_surplus >= goal_monthly_required if goal_monthly_required > 0 else None
    goal_feasible_after = new_monthly_surplus >= goal_monthly_required if goal_monthly_required > 0 else None

    return {
        "scope": _scope(scope),
        "period": _period_payload(period),
        "income_delta": round(income_delta, 2),
        "before": {
            "monthly_income": round(monthly_income, 2),
            "monthly_spent": round(monthly_spent, 2),
            "monthly_surplus": round(monthly_surplus, 2),
            "savings_rate_pct": savings_rate_before,
        },
        "after": {
            "monthly_income": round(new_monthly_income, 2),
            "monthly_spent": round(monthly_spent, 2),
            "monthly_surplus": round(new_monthly_surplus, 2),
            "savings_rate_pct": savings_rate_after,
        },
        "goal_impact": {
            "active_goal_monthly_required": round(goal_monthly_required, 2),
            "feasible_before": goal_feasible_before,
            "feasible_after": goal_feasible_after,
        } if active_goals else None,
        "limitations": [LIMITATION, "Mô phỏng giả định chi tiêu không thay đổi khi thu nhập thay đổi."],
    }


def get_spending_patterns(
    user_id: str,
    *,
    scope: str = "90d",
    group_by: str = "weekday",
) -> dict[str, Any]:
    """Phân tích pattern chi tiêu theo thứ trong tuần hoặc ngày trong tháng."""
    valid_group_by = {"weekday", "day_of_month", "week_of_month"}
    if group_by not in valid_group_by:
        group_by = "weekday"
    period = _period_for_scope(scope if scope in {"cycle", "90d", "ytd"} else "90d")
    rows = [row for row in _transaction_rows_for_period(user_id, period) if row["amount"] < 0]

    if group_by == "weekday":
        weekday_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
        buckets: dict[str, dict[str, Any]] = {name: {"label": name, "total": 0.0, "count": 0, "days_seen": set()} for name in weekday_names}
        for row in rows:
            # weekday(): 0=Monday … 6=Sunday
            name = weekday_names[row["date"].weekday()]
            buckets[name]["total"] += abs(row["amount"])
            buckets[name]["count"] += 1
            buckets[name]["days_seen"].add(row["date"])
        result_buckets = []
        for name in weekday_names:
            b = buckets[name]
            days_count = len(b["days_seen"])
            result_buckets.append({
                "label": name,
                "total": round(b["total"], 2),
                "transaction_count": b["count"],
                "avg_per_day": round(b["total"] / days_count, 2) if days_count > 0 else 0.0,
            })
        weekend_days = {"Thứ 7", "Chủ nhật"}
        weekend_total = sum(b["total"] for n, b in buckets.items() if n in weekend_days)
        weekend_day_count = sum(len(b["days_seen"]) for n, b in buckets.items() if n in weekend_days)
        weekday_total = sum(b["total"] for n, b in buckets.items() if n not in weekend_days)
        weekday_day_count = sum(len(b["days_seen"]) for n, b in buckets.items() if n not in weekend_days)
        weekend_avg = round(weekend_total / weekend_day_count, 2) if weekend_day_count > 0 else 0.0
        weekday_avg = round(weekday_total / weekday_day_count, 2) if weekday_day_count > 0 else 0.0
        ratio = round(weekend_avg / weekday_avg, 2) if weekday_avg > 0 else None
        extra = {"weekend_vs_weekday": {"weekend_avg_per_day": weekend_avg, "weekday_avg_per_day": weekday_avg, "ratio": ratio}}

    elif group_by == "day_of_month":
        day_buckets: dict[int, dict[str, Any]] = {d: {"total": 0.0, "count": 0} for d in range(1, 32)}
        for row in rows:
            d = row["date"].day
            day_buckets[d]["total"] += abs(row["amount"])
            day_buckets[d]["count"] += 1
        result_buckets = [
            {"label": f"Ngày {d}", "total": round(day_buckets[d]["total"], 2), "transaction_count": day_buckets[d]["count"], "avg_per_day": round(day_buckets[d]["total"], 2)}
            for d in range(1, 32) if day_buckets[d]["count"] > 0
        ]
        extra = {}

    else:  # week_of_month
        week_names = ["Tuần 1 (1-7)", "Tuần 2 (8-14)", "Tuần 3 (15-21)", "Tuần 4 (22+)"]
        week_buckets: dict[str, dict[str, Any]] = {w: {"total": 0.0, "count": 0} for w in week_names}
        for row in rows:
            d = row["date"].day
            if d <= 7:
                w = week_names[0]
            elif d <= 14:
                w = week_names[1]
            elif d <= 21:
                w = week_names[2]
            else:
                w = week_names[3]
            week_buckets[w]["total"] += abs(row["amount"])
            week_buckets[w]["count"] += 1
        result_buckets = [{"label": w, "total": round(week_buckets[w]["total"], 2), "transaction_count": week_buckets[w]["count"], "avg_per_day": round(week_buckets[w]["total"] / 7, 2)} for w in week_names]
        extra = {}

    peak = max(result_buckets, key=lambda b: b["total"], default=None) if result_buckets else None
    return {
        "scope": _scope(scope),
        "period": _period_payload(period),
        "group_by": group_by,
        "buckets": result_buckets,
        "peak": {"label": peak["label"], "total": peak["total"]} if peak else None,
        **extra,
        "limitations": [LIMITATION] if rows else ["Khong co du lieu giao dich de phan tich.", LIMITATION],
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
    rows = []
    for key in keys:
        a_val = round(_as_float(current.get(key)), 2)
        b_val = round(_as_float(previous.get(key)), 2)
        delta = round(a_val - b_val, 2)
        pct, pct_label = _pct_delta_with_label(a_val, b_val)
        rows.append({
            key_name: key,
            "period_a_amount": a_val,
            "period_b_amount": b_val,
            "delta": delta,
            "delta_pct": pct,
            "delta_pct_label": pct_label,
        })
    rows.sort(key=lambda item: abs(_as_float(item["delta"])), reverse=True)
    return rows[:5]


def _is_partial_period(period_a_start: date, period_a_end: date, today: date) -> bool:
    """
    Partial nếu period_a chưa kết thúc tự nhiên — tức end_date
    nằm trong tháng hiện tại hoặc sau today.
    Full month đã qua (end <= first of current month) không phải partial.
    """
    current_month_start = today.replace(day=1)
    return period_a_end > current_month_start and period_a_end <= today


def _comparison_periods(
    a_from: str,
    a_to: str,
    b_from: str,
    b_to: str,
    force_no_align: bool = False,
) -> ComparisonPeriods:
    today = get_today_in_user_timezone()
    
    if a_from and a_to and b_from and b_to:
        p_a = (_parse_date(a_from), _parse_date(a_to))
        p_b = (_parse_date(b_from), _parse_date(b_to))
    else:
        # Default MTD
        current_month_start = today.replace(day=1)
        period_a_start = current_month_start
        period_a_end = today + timedelta(days=1)  # exclusive

        previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)
        period_b_start = previous_month_start
        period_b_end = previous_month_start + (period_a_end - period_a_start)  # MTD aligned
        p_a = (period_a_start, period_a_end)
        p_b = (period_b_start, period_b_end)

    # Chronological sorting
    was_swapped = False
    if p_a[0] < p_b[0]:
        p_a, p_b = p_b, p_a
        was_swapped = True

    was_aligned = False
    limitations = []
    
    period_a_start = p_a[0]
    period_a_end = p_a[1]
    period_b_start = p_b[0]
    period_b_end = p_b[1]
    
    should_align = (
        not force_no_align
        and _is_partial_period(period_a_start, period_a_end, today)
        and period_b_end > period_b_start
        and (period_a_end - period_a_start).days <= 31
    )
    
    if should_align:
        period_a_days = (period_a_end - period_a_start).days
        period_b_end_aligned = period_b_start + timedelta(days=period_a_days)
        
        if period_b_end_aligned > period_b_end:
            limitations.append("period_b shorter than period_a, comparison may be skewed")
        else:
            period_b_end = period_b_end_aligned
            was_aligned = True

    return ComparisonPeriods(
        period_a_start=period_a_start,
        period_a_end=period_a_end,
        period_b_start=period_b_start,
        period_b_end=period_b_end,
        was_swapped=was_swapped,
        was_aligned=was_aligned,
        limitations=limitations,
    )


def _period_for_scope(scope: str) -> tuple[date, date]:
    normalized = _scope(scope)
    today = get_today_in_user_timezone()
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


def _pct_delta_with_label(a_val: float, b_val: float) -> tuple[float | None, str]:
    a_val = _as_float(a_val)
    b_val = _as_float(b_val)
    if b_val == 0.0 and a_val > 0.0:
        return None, "new_spending"
    elif a_val == 0.0 and b_val > 0.0:
        return -100.0, "stopped_spending"
    elif a_val == 0.0 and b_val == 0.0:
        return None, "no_activity"
    else:
        if b_val == 0.0:
            return None, "normal"
        return round((a_val - b_val) / b_val * 100, 1), "normal"


def _scope(value: str) -> str:
    normalized = str(value or "cycle").strip().lower()
    return normalized if normalized in {"cycle", "90d", "ytd"} else "cycle"


def _parse_date_or_today(value: str) -> date:
    if not str(value or "").strip():
        return get_today_in_user_timezone()
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
