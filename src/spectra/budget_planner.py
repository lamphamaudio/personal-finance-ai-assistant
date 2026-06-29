"""Deterministic budget recommendation and adjustment helpers."""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

from spectra.categories import (
    ENTERTAINMENT,
    FOOD,
    HOUSING,
    OTHER,
    SHOPPING,
    TRANSPORT,
    UTILITIES,
)

LIMITATION = "Day la goi y quan ly ngan sach dua tren du lieu hien co, khong phai tu van tai chinh chuyen nghiep."

FIXED_CATEGORIES = {"nha cua", "tien thue nha", "hoa don", "tra no", "giao duc", "suc khoe", "bao hiem", "dien nuoc"}
FLEXIBLE_CATEGORIES = {"an uong", "ca phe", "dat do an", "mua sam", "giai tri", "subscriptions", "khac", "dich vu"}

# Minimum number of historical spending categories before we trust history-based
# allocation. Below this we fall back to a standard template so new users still get
# a multi-category plan instead of a single-category one.
MIN_HISTORY_CATEGORIES = 3

# Standard split of the spend-able amount across typical categories. Shares sum to 1.0.
BUDGET_TEMPLATE_SHARES: tuple[tuple[str, float], ...] = (
    (FOOD, 0.30),
    (HOUSING, 0.22),
    (TRANSPORT, 0.12),
    (SHOPPING, 0.10),
    (UTILITIES, 0.10),
    (ENTERTAINMENT, 0.08),
    (OTHER, 0.08),
)


def get_budget_status_for_chat(
    user_id: str,
    *,
    scope: str = "cycle",
    summary_payload: dict[str, Any] | None = None,
    budget_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del user_id
    scope = _scope(scope)
    summary = summary_payload or {}
    budget = budget_payload or {"items": [], "current_cycle": {}}
    period = _period(summary, budget, scope)
    currency = str(summary.get("currency") or summary.get("base_currency") or "VND")
    total_spent = _as_float(summary.get("total_spent"))
    elapsed, total_days = _period_days(period)
    categories = []
    alerts = []
    total_budget = 0.0
    projected_total = 0.0
    for item in list(budget.get("items") or []):
        category = str(item.get("category") or "")
        spent = _as_float(item.get("spent"))
        limit = _as_float(item.get("limit"))
        pct = (spent / limit * 100) if limit > 0 else None
        projected = spent / elapsed * total_days if elapsed > 0 else spent
        over_projected = max(projected - limit, 0) if limit > 0 else 0
        if limit > 0:
            total_budget += limit
        projected_total += projected
        status = _budget_status(spent, limit, projected)
        if status in {"over", "at_risk"}:
            alerts.append(f"{category} co nguy co vuot ngan sach.")
        categories.append(
            {
                "category": category,
                "budget_limit": round(limit, 2) if limit else None,
                "actual_spend": round(spent, 2),
                "remaining": round(limit - spent, 2) if limit else None,
                "usage_percentage": round(pct, 1) if pct is not None else None,
                "projected_spend": round(projected, 2),
                "projected_over_budget_amount": round(over_projected, 2),
                "status": status,
                "recommendation": _category_status_recommendation(category, spent, limit, projected),
            }
        )
    remaining = total_budget - total_spent if total_budget else None
    return {
        "scope": scope,
        "period": period,
        "currency": currency,
        "summary": {
            "total_budget": round(total_budget, 2),
            "total_spent": round(total_spent, 2),
            "remaining_budget": round(remaining, 2) if remaining is not None else None,
            "usage_percentage": round(total_spent / total_budget * 100, 1) if total_budget > 0 else None,
            "projected_total_spend": round(projected_total, 2),
            "projected_over_budget": round(max(projected_total - total_budget, 0), 2) if total_budget > 0 else None,
        },
        "categories": categories,
        "alerts": alerts[:5],
        "missing_data": [] if total_budget > 0 else ["budget_limits"],
        "limitations": [LIMITATION, "Du bao ngan sach dua tren toc do chi tieu hien tai va co the thay doi."],
    }


def recommend_budget_plan(
    user_id: str,
    *,
    scope: str = "cycle",
    target_savings_amount: float | None = None,
    monthly_income: float | None = None,
    goal_id: str | None = None,
    summary_payload: dict[str, Any] | None = None,
    budget_payload: dict[str, Any] | None = None,
    goals_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del user_id, goal_id
    scope = _scope(scope)
    summary = summary_payload or {}
    budget = budget_payload or {"items": []}
    goals = list((goals_payload or {}).get("goals") or [])
    currency = str(summary.get("currency") or summary.get("base_currency") or "VND")
    # A user-stated monthly income (e.g. "lương 8tr") overrides the income derived
    # from transaction history, which is often 0 for new users.
    stated_income = _as_float(monthly_income)
    income = stated_income if stated_income > 0 else _as_float(summary.get("total_income"))
    income_source = "user_stated" if stated_income > 0 else "transactions"
    total_spent = _as_float(summary.get("total_spent"))
    by_category = {str(k): abs(_as_float(v)) for k, v in (summary.get("by_category") or {}).items()}
    budget_by_cat = {str(item.get("category")): _as_float(item.get("limit")) for item in budget.get("items") or []}
    target_savings = _target_savings(target_savings_amount, goals, income)
    available = max(income - target_savings, 0) if income > 0 else 0

    # Fall back to a standard template when there is too little spending history to
    # build a meaningful per-category plan (otherwise the plan covers only the one or
    # two categories the user has spent in).
    if available > 0 and len(by_category) < MIN_HISTORY_CATEGORIES:
        recommendations = _template_recommendations(available, by_category, budget_by_cat)
        strategy = "template_budget"
    else:
        recommendations = []
        total_basis = sum(by_category.values()) or total_spent
        for category, spend in sorted(by_category.items(), key=lambda item: -item[1]):
            share = (spend / total_basis) if total_basis > 0 else 0
            adjusted_share = _adjusted_share(category, share)
            recommended = available * adjusted_share if available > 0 else max(spend * 0.9, 0)
            if _is_fixed(category):
                recommended = max(recommended, spend * 0.9)
            else:
                recommended = max(recommended, spend * 0.65)
            current_budget = budget_by_cat.get(category) or 0
            change_base = current_budget if current_budget > 0 else spend
            recommendations.append(
                {
                    "category": category,
                    "current_spend": round(spend, 2),
                    "current_budget": round(current_budget, 2) if current_budget else None,
                    "recommended_budget": round(recommended, 2),
                    "suggested_change": round(recommended - change_base, 2),
                    "difficulty": _difficulty(category, recommended, spend),
                    "reason": _recommendation_reason(category),
                }
            )
        strategy = "goal_aware_budget"

    recommendations.sort(key=lambda item: (_is_fixed(str(item["category"])), item["suggested_change"]))
    estimated_saving = sum(max(_as_float(item["current_spend"]) - _as_float(item["recommended_budget"]), 0) for item in recommendations)
    limitations = [LIMITATION]
    if strategy == "template_budget":
        limitations.append("Ke hoach chia theo mau ngan sach chuan vi chua du lich su chi tieu cua ban.")
    return {
        "scope": scope,
        "strategy": strategy,
        "currency": currency,
        "summary": {
            "total_income": round(income, 2),
            "income_source": income_source,
            "target_savings": round(target_savings, 2),
            "available_for_spending": round(available, 2),
            "confidence": "medium" if income > 0 else "low",
        },
        "recommended_budgets": recommendations[:20],
        "impact": {
            "estimated_monthly_saving": round(estimated_saving, 2),
            "goal_feasibility_before": None,
            "goal_feasibility_after": None,
        },
        "risks": _recommendation_risks(recommendations),
        "next_actions": _budget_next_actions(recommendations, currency),
        "missing_data": [] if income > 0 else ["income"],
        "limitations": limitations,
    }


def _template_recommendations(
    available: float,
    by_category: dict[str, float],
    budget_by_cat: dict[str, float],
) -> list[dict[str, Any]]:
    """Allocate *available* across a standard category template (history too sparse)."""
    history_by_fold = {_fold(name): amount for name, amount in by_category.items()}
    recommendations: list[dict[str, Any]] = []
    for category, share in BUDGET_TEMPLATE_SHARES:
        recommended = available * share
        spend = history_by_fold.get(_fold(category), 0.0)
        current_budget = budget_by_cat.get(category) or 0
        change_base = current_budget if current_budget > 0 else spend
        recommendations.append(
            {
                "category": category,
                "current_spend": round(spend, 2),
                "current_budget": round(current_budget, 2) if current_budget else None,
                "recommended_budget": round(recommended, 2),
                "suggested_change": round(recommended - change_base, 2),
                "difficulty": _difficulty(category, recommended, spend),
                "reason": "Phan bo theo mau ngan sach chuan vi chua du lich su chi tieu.",
            }
        )
    return recommendations


def simulate_budget_adjustment(
    user_id: str,
    *,
    adjustments: list[dict[str, Any]],
    scope: str = "cycle",
    goal_id: str | None = None,
    summary_payload: dict[str, Any] | None = None,
    budget_payload: dict[str, Any] | None = None,
    goals_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = get_budget_status_for_chat(user_id, scope=scope, summary_payload=summary_payload, budget_payload=budget_payload)
    adjusted_items = [dict(item) for item in (budget_payload or {}).get("items", [])]
    for adjustment in adjustments or []:
        category = str(adjustment.get("category") or "").strip()
        limit = _non_negative(adjustment.get("limit"), "limit")
        found = False
        for item in adjusted_items:
            if _fold(str(item.get("category"))) == _fold(category):
                item["limit"] = limit
                found = True
        if not found:
            adjusted_items.append({"category": category, "spent": 0, "limit": limit, "status": "none"})
    adjusted_payload = {**(budget_payload or {}), "items": adjusted_items}
    adjusted = get_budget_status_for_chat(user_id, scope=scope, summary_payload=summary_payload, budget_payload=adjusted_payload)
    base_total = _as_float(base["summary"].get("total_budget"))
    adjusted_total = _as_float(adjusted["summary"].get("total_budget"))
    return {
        "scope": _scope(scope),
        "goal_id": goal_id,
        "base_status": base,
        "adjusted_status": adjusted,
        "adjustments": [{"category": str(a.get("category") or ""), "limit": _as_float(a.get("limit"))} for a in adjustments or []],
        "impact": {
            "budget_delta": round(adjusted_total - base_total, 2),
            "estimated_saving_change": round(base_total - adjusted_total, 2),
            "projected_over_budget_before": base["summary"].get("projected_over_budget"),
            "projected_over_budget_after": adjusted["summary"].get("projected_over_budget"),
        },
        "limitations": [LIMITATION, "Mo phong khong cap nhat ngan sach that."],
    }


def compare_budget_vs_actual(user_id: str, *, scope: str = "cycle", summary_payload: dict[str, Any] | None = None, budget_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_budget_status_for_chat(user_id, scope=scope, summary_payload=summary_payload, budget_payload=budget_payload)


def update_budget_limit(user_id: str, *, category: str, limit: float) -> dict[str, Any]:
    from spectra.web import server

    scoped_user = str(user_id or "")
    clean_category = _validate_category(category)
    amount = _non_negative(limit, "limit")
    with server._get_db() as db:
        db.save_budget_limit(clean_category, amount, user_id=scoped_user)
    return {"ok": True, "category": clean_category, "limit": round(amount, 2)}


def upsert_budget_plan(user_id: str, *, budgets: list[dict[str, Any]], scope: str = "cycle") -> dict[str, Any]:
    del scope
    if not budgets:
        raise ValueError("budgets must not be empty")
    if len(budgets) > 20:
        raise ValueError("Too many budget items")
    updated = [update_budget_limit(user_id, category=str(item.get("category") or ""), limit=item.get("limit")) for item in budgets]
    return {"ok": True, "updated": updated}


def parse_budget_limit_request(message: str) -> dict[str, Any] | None:
    normalized = _fold(message)
    if "ngan sach" not in normalized:
        return None
    import re

    match = re.search(r"ngan sach\s+(.+?)\s+(?:xuong|la|thanh|muc)?\s*(\d+(?:[.,]\d+)?)\s*(trieu|m|k|nghin|ngan)?", normalized)
    if not match:
        return None
    category = match.group(1).strip()
    amount = float(match.group(2).replace(",", "."))
    unit = match.group(3) or ""
    if unit in {"trieu", "m"}:
        amount *= 1_000_000
    elif unit in {"k", "nghin", "ngan"}:
        amount *= 1_000
    return {"category": category, "limit": amount}


def _budget_status(spent: float, limit: float, projected: float) -> str:
    if limit <= 0:
        return "no_limit"
    if spent >= limit:
        return "over"
    if projected > limit or spent / limit >= 0.8:
        return "at_risk"
    return "on_track"


def _category_status_recommendation(category: str, spent: float, limit: float, projected: float) -> str:
    if limit <= 0:
        return "Chua co han muc cho danh muc nay."
    if spent >= limit:
        return f"{category} da vuot ngan sach, nen tam giam chi tieu phat sinh."
    if projected > limit:
        return f"Nen giam khoang {projected - limit:,.0f} VND trong phan con lai cua ky."
    return "Dang trong ngan sach."


def _target_savings(explicit: float | None, goals: list[dict[str, Any]], income: float) -> float:
    if explicit is not None:
        return max(_as_float(explicit), 0)
    active_required = [_as_float(goal.get("monthly_required_amount")) for goal in goals if goal.get("status") == "active"]
    if active_required:
        return max(active_required)
    return income * 0.15 if income > 0 else 0


def _adjusted_share(category: str, share: float) -> float:
    if _is_fixed(category):
        return share * 1.05
    if _is_flexible(category):
        return share * 0.9
    return share


def _recommendation_reason(category: str) -> str:
    if _is_fixed(category):
        return "Day la nhom chi co dinh, khong nen cat giam manh."
    if _is_flexible(category):
        return "Day la nhom linh hoat co the toi uu tung buoc."
    return "De xuat dua tren ty trong chi tieu hien tai."


def _difficulty(category: str, recommended: float, spend: float) -> str:
    if _is_fixed(category):
        return "hard"
    if spend <= 0:
        return "low"
    ratio = recommended / spend
    if ratio >= 0.9:
        return "low"
    if ratio >= 0.7:
        return "medium"
    return "hard"


def _recommendation_risks(recommendations: list[dict[str, Any]]) -> list[str]:
    risks = []
    for item in recommendations[:5]:
        if item["difficulty"] == "hard" and not _is_fixed(str(item["category"])):
            risks.append(f"Cat giam qua manh nhom {item['category']} co the kho duy tri.")
    return risks[:3]


def _budget_next_actions(recommendations: list[dict[str, Any]], currency: str) -> list[str]:
    actions = []
    for item in recommendations[:3]:
        actions.append(f"Dat ngan sach {item['category']} khoang {_as_float(item['recommended_budget']):,.0f} {currency}.")
    actions.append("Theo doi chi tieu moi tuan va dieu chinh sau 1 chu ky neu qua kho duy tri.")
    return actions[:3]


def _period(summary: dict[str, Any], budget: dict[str, Any], scope: str) -> dict[str, str]:
    period = summary.get("selected_period") or budget.get("current_cycle") or {}
    return {
        "start": str(period.get("start") or date.today().replace(day=1).isoformat()),
        "end": str(period.get("end") or date.today().isoformat()),
        "label": str(period.get("label") or scope),
    }


def _period_days(period: dict[str, str]) -> tuple[int, int]:
    try:
        start = date.fromisoformat(str(period["start"])[:10])
        end = date.fromisoformat(str(period["end"])[:10])
    except (KeyError, ValueError):
        return 1, 30
    total = max((end - start).days, 1)
    elapsed = min(max((date.today() - start).days + 1, 1), total)
    return elapsed, total


def _validate_category(category: str) -> str:
    clean = str(category or "").strip()
    if not clean:
        raise ValueError("category is required")
    return clean


def _non_negative(value: Any, name: str) -> float:
    amount = _as_float(value)
    if amount < 0:
        raise ValueError(f"{name} must be non-negative")
    return amount


def _is_fixed(category: str) -> bool:
    return _fold(category) in FIXED_CATEGORIES


def _is_flexible(category: str) -> bool:
    return _fold(category) in FLEXIBLE_CATEGORIES


def _scope(value: str) -> str:
    normalized = str(value or "cycle").strip().lower()
    return normalized if normalized in {"cycle", "90d", "ytd"} else "cycle"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _fold(value: str) -> str:
    value = str(value or "").replace("đ", "d").replace("Đ", "D")
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(folded.lower().split())
