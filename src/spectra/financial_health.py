"""Deterministic financial health score service."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


MAX_COMPONENTS = {
    "savings_rate": 25,
    "net_cashflow": 20,
    "spending_control": 15,
    "category_balance": 15,
    "anomaly_risk": 10,
    "forecast_risk": 10,
    "budget_discipline": 5,
}

LEVELS = [
    (0, 39, "Yeu"),
    (40, 59, "Can cai thien"),
    (60, 74, "Trung binh kha"),
    (75, 89, "Tot"),
    (90, 100, "Rat tot"),
]

DISCLAIMER = (
    "Diem so nay chi la cong cu tham khao quan ly chi tieu va dong tien ca nhan, "
    "khong phai tu van tai chinh chuyen nghiep hay diem tin dung."
)


def calculate_financial_health_score(
    user_id: str,
    *,
    scope: str = "cycle",
    month: str | None = None,
    summary_payload: dict[str, Any] | None = None,
    anomaly_payload: dict[str, Any] | None = None,
    forecast_payload: dict[str, Any] | None = None,
    budget_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_scope = _normalize_scope(scope)
    summary_payload = summary_payload or _empty_summary(normalized_scope)
    anomaly_payload = anomaly_payload or {"anomalies": [], "summary": {"total": 0, "high": 0}}
    forecast_payload = forecast_payload or {"available": False}
    budget_payload = budget_payload or {"items": []}

    total_income = _as_float(summary_payload.get("total_income"))
    total_spent = _as_float(summary_payload.get("total_spent"))
    net_cashflow = total_income - total_spent
    savings_rate = net_cashflow / total_income if total_income > 0 else None

    components = [
        score_savings_rate(total_income, net_cashflow),
        score_net_cashflow(net_cashflow, total_income),
        score_spending_control(summary_payload),
        score_category_balance(summary_payload.get("by_category") or {}, total_spent),
        score_anomaly_risk(anomaly_payload),
        score_forecast_risk(forecast_payload),
        score_budget_discipline(budget_payload),
    ]
    available = [component for component in components if component.get("available", True)]
    available_max = sum(int(component["max_score"]) for component in available)
    raw_score = sum(float(component["score"]) for component in available)
    score = int(round((raw_score / available_max) * 100)) if available_max else 0
    score = min(max(score, 0), 100)

    missing_data = []
    for component in components:
        if not component.get("available", True):
            missing_data.append(str(component["name"]))
    if total_income <= 0:
        missing_data.append("income")
    if forecast_payload.get("available") is False:
        missing_data.append("forecast")

    strengths = _build_strengths(components, net_cashflow, savings_rate)
    risks = _build_risks(components, anomaly_payload, forecast_payload)
    actions = _build_recommended_actions(components, risks)

    forecasted_balance = forecast_payload.get("predicted_end_of_month_balance")
    period = _period_from_summary(summary_payload, normalized_scope, month)
    return {
        "scope": normalized_scope,
        "period": period,
        "score": score,
        "level": score_level(score),
        "confidence": _confidence(available, missing_data),
        "components": components,
        "summary": {
            "total_income": round(total_income, 2),
            "total_spent": round(total_spent, 2),
            "net_cashflow": round(net_cashflow, 2),
            "savings_rate": round(savings_rate, 4) if savings_rate is not None else None,
            "anomaly_count": int((anomaly_payload.get("summary") or {}).get("total") or 0),
            "forecasted_end_balance": _round_or_none(forecasted_balance),
        },
        "strengths": strengths,
        "risks": risks,
        "recommended_actions": actions,
        "missing_data": sorted(set(missing_data)),
        "limitations": [
            DISCLAIMER,
            "Diem so duoc tinh tu du lieu hien co va co the thay doi khi giao dich moi duoc dong bo.",
        ],
    }


def score_savings_rate(total_income: float, net_cashflow: float) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["savings_rate"]
    if total_income <= 0:
        return _component("savings_rate", "Ty le tiet kiem", 0, max_score, None, "unavailable", "Chua co du lieu thu nhap.", False)
    rate = net_cashflow / total_income
    if rate >= 0.30:
        score, level = 25, "excellent"
    elif rate >= 0.20:
        score, level = 20, "good"
    elif rate >= 0.10:
        score, level = 15, "medium"
    elif rate >= 0:
        score, level = 8, "low"
    else:
        score, level = 0, "risk"
    return _component(
        "savings_rate",
        "Ty le tiet kiem",
        score,
        max_score,
        round(rate, 4),
        level,
        f"Ban giu lai khoang {rate * 100:.0f}% thu nhap trong ky.",
    )


def score_net_cashflow(net_cashflow: float, total_income: float) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["net_cashflow"]
    if net_cashflow > 0:
        score, level = 20, "good"
    elif net_cashflow == 0:
        score, level = 10, "medium"
    elif total_income > 0 and abs(net_cashflow) <= total_income * 0.1:
        score, level = 5, "low"
    else:
        score, level = 0, "risk"
    return _component("net_cashflow", "Dong tien rong", score, max_score, round(net_cashflow, 2), level, "Dong tien rong duoc tinh bang thu nhap tru chi tieu.")


def score_spending_control(summary_payload: dict[str, Any]) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["spending_control"]
    burn_rate = summary_payload.get("burn_rate") or {}
    status = str(burn_rate.get("status") or "").lower()
    projected = _as_float(burn_rate.get("projected_total") or burn_rate.get("projected_spend"))
    spent = _as_float(summary_payload.get("total_spent"))
    if not burn_rate:
        return _component("spending_control", "Kiem soat chi tieu", 9, max_score, None, "medium", "Chua co burn rate day du nen dung diem trung tinh.")
    if status in {"good", "on_track", "stable"}:
        score, level = 15, "good"
    elif status in {"warning", "watch"}:
        score, level = 9, "medium"
    elif status in {"danger", "over"}:
        score, level = 3, "risk"
    elif projected and spent and projected <= spent * 1.1:
        score, level = 12, "good"
    else:
        score, level = 8, "medium"
    return _component("spending_control", "Kiem soat chi tieu", score, max_score, status or None, level, "Diem nay dua tren toc do chi tieu hien tai.")


def score_category_balance(by_category: dict[str, Any], total_spent: float) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["category_balance"]
    if total_spent <= 0 or not by_category:
        return _component("category_balance", "Can bang danh muc", 0, max_score, None, "unavailable", "Chua co du lieu chi tieu theo danh muc.", False)
    normalized = {str(k): abs(_as_float(v)) for k, v in by_category.items()}
    category, amount = max(normalized.items(), key=lambda item: item[1])
    share = amount / total_spent if total_spent else 0
    fixed = _fold(category) in {"rent", "housing", "nha", "tien nha", "dien nuoc"}
    if share > 0.60 and not fixed:
        score, level = 4, "risk"
    elif share > 0.60 and fixed:
        score, level = 9, "medium"
    elif share >= 0.40:
        score, level = 9, "medium"
    else:
        score, level = 15, "good"
    return _component("category_balance", "Can bang danh muc", score, max_score, round(share, 4), level, f"Danh muc lon nhat la {category}, chiem khoang {share * 100:.0f}% chi tieu.")


def score_anomaly_risk(anomaly_payload: dict[str, Any]) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["anomaly_risk"]
    summary = anomaly_payload.get("summary") or {}
    count = int(summary.get("total") or len(anomaly_payload.get("anomalies") or []))
    high = int(summary.get("high") or 0)
    if count <= 0:
        score, level = 10, "good"
    elif high >= 2:
        score, level = 1, "risk"
    elif high >= 1 or count >= 4:
        score, level = 4, "medium"
    else:
        score, level = 7, "low"
    return _component("anomaly_risk", "Rui ro bat thuong", score, max_score, {"count": count, "high": high}, level, f"Co {count} giao dich bat thuong trong pham vi hien tai.")


def score_forecast_risk(forecast_payload: dict[str, Any]) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["forecast_risk"]
    if forecast_payload.get("available") is False:
        return _component("forecast_risk", "Rui ro du bao", 0, max_score, None, "unavailable", "Chua co du lieu du bao so du.", False)
    balance = _as_float(forecast_payload.get("predicted_end_of_month_balance"))
    current = _as_float(forecast_payload.get("current_balance"))
    if balance < 0:
        score, level = 0, "risk"
    elif current > 0 and balance < current * 0.2:
        score, level = 4, "low"
    elif balance <= 0:
        score, level = 2, "risk"
    else:
        score, level = 10, "good"
    return _component("forecast_risk", "Rui ro du bao", score, max_score, round(balance, 2), level, "Du bao so du cuoi thang chi la uoc tinh.")


def score_budget_discipline(budget_payload: dict[str, Any]) -> dict[str, Any]:
    max_score = MAX_COMPONENTS["budget_discipline"]
    items = list(budget_payload.get("items") or [])
    if not items:
        return _component("budget_discipline", "Ky luat ngan sach", 3, max_score, None, "neutral", "Chua co ngan sach chi tiet nen dung diem trung tinh.")
    over = sum(1 for item in items if str(item.get("status") or "").lower() in {"over", "danger"})
    if over == 0:
        score, level = 5, "good"
    elif over <= 2:
        score, level = 3, "medium"
    else:
        score, level = 1, "risk"
    return _component("budget_discipline", "Ky luat ngan sach", score, max_score, {"over": over}, level, f"Co {over} danh muc vuot ngan sach.")


def score_level(score: int) -> str:
    for minimum, maximum, label in LEVELS:
        if minimum <= score <= maximum:
            return label
    return "Yeu"


def _component(name: str, label: str, score: float, max_score: int, value: Any, level: str, explanation: str, available: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "score": round(score, 2),
        "max_score": max_score,
        "value": value,
        "level": level,
        "explanation": explanation,
        "available": available,
    }


def _build_strengths(components: list[dict[str, Any]], net_cashflow: float, savings_rate: float | None) -> list[str]:
    strengths = []
    if net_cashflow > 0:
        strengths.append("Dong tien van duong.")
    if savings_rate is not None and savings_rate >= 0.2:
        strengths.append("Ty le tiet kiem dang o muc tot.")
    for component in components:
        if component.get("available", True) and float(component.get("score") or 0) >= float(component.get("max_score") or 1) * 0.8:
            strengths.append(str(component["label"]) + " dang on.")
    return _dedupe(strengths)[:3]


def _build_risks(components: list[dict[str, Any]], anomaly_payload: dict[str, Any], forecast_payload: dict[str, Any]) -> list[str]:
    risks = []
    anomaly_count = int((anomaly_payload.get("summary") or {}).get("total") or 0)
    if anomaly_count:
        risks.append(f"Co {anomaly_count} giao dich bat thuong can kiem tra.")
    if forecast_payload.get("available") is True and _as_float(forecast_payload.get("predicted_end_of_month_balance")) < 0:
        risks.append("So du uoc tinh cuoi thang co nguy co am.")
    for component in components:
        if component.get("available", True) and float(component.get("score") or 0) <= float(component.get("max_score") or 1) * 0.35:
            risks.append(str(component["label"]) + " dang yeu.")
    return _dedupe(risks)[:3]


def _build_recommended_actions(components: list[dict[str, Any]], risks: list[str]) -> list[str]:
    names = {component["name"]: component for component in components}
    actions = []
    if names["anomaly_risk"]["score"] < 10:
        actions.append("Kiem tra lai cac giao dich bat thuong trong ky.")
    if names["savings_rate"].get("available") and names["savings_rate"]["score"] < 20:
        actions.append("Dat muc tieu tiet kiem toi thieu 20% thu nhap neu kha thi.")
    if names["category_balance"].get("available") and names["category_balance"]["score"] < 10:
        actions.append("Dat gioi han theo tuan cho danh muc chi lon nhat.")
    if names["forecast_risk"].get("available") and names["forecast_risk"]["score"] < 5:
        actions.append("Giam cac khoan chi khong thiet yeu truoc cuoi thang.")
    if not actions and not risks:
        actions.append("Tiep tuc theo doi chi tieu va giu muc tiet kiem hien tai.")
    return actions[:3]


def _confidence(available: list[dict[str, Any]], missing_data: list[str]) -> str:
    if len(available) >= 6 and len(missing_data) <= 1:
        return "high"
    if len(available) >= 4:
        return "medium"
    return "low"


def _period_from_summary(summary: dict[str, Any], scope: str, month: str | None) -> dict[str, str]:
    cycle = summary.get("current_cycle") or {}
    if cycle.get("start") and cycle.get("end"):
        return {"start": str(cycle["start"]), "end": str(cycle["end"]), "label": str(cycle.get("label") or scope)}
    today = date.today()
    if month:
        try:
            year, month_num = [int(part) for part in month.split("-", 1)]
            start = date(year, month_num, 1)
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            return {"start": start.isoformat(), "end": end.isoformat(), "label": month}
        except ValueError:
            pass
    start = today.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {"start": start.isoformat(), "end": end.isoformat(), "label": scope}


def _empty_summary(scope: str) -> dict[str, Any]:
    return {"scope": scope, "total_income": 0, "total_spent": 0, "by_category": {}}


def _normalize_scope(scope: str) -> str:
    normalized = str(scope or "cycle").strip().lower()
    return normalized if normalized in {"cycle", "90d", "ytd"} else "cycle"


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return round(_as_float(value), 2)


def _fold(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output
