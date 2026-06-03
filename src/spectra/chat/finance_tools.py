"""Read-only finance data services for chatbot anomaly and forecast tools."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def get_anomalies_for_chat(user_id: str, *, limit: int = 10, scope: str = "cycle") -> dict[str, Any]:
    from spectra.web import server

    safe_limit = min(max(_as_int(limit, 10), 1), 20)
    date_filter = _scope_start_date(scope)
    where = ["user_id = ?", "is_anomaly = TRUE"]
    params: list[Any] = [user_id]
    if date_filter:
        where.append("created_at >= ?")
        params.append(date_filter.isoformat())

    with server._get_db() as db:
        rows = db._conn.execute(
            f"""
            SELECT id, created_at, merchant, amount, category, anomaly_reason
            FROM bank_transactions
            WHERE {" AND ".join(where)}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            [*params, safe_limit],
        ).fetchall()

    anomalies = [_normalize_bank_anomaly(row) for row in rows]
    summary = {
        "total": len(anomalies),
        "high": sum(1 for item in anomalies if item["severity"] == "high"),
        "medium": sum(1 for item in anomalies if item["severity"] == "medium"),
        "low": sum(1 for item in anomalies if item["severity"] == "low"),
    }
    limitations: list[str] = []
    if not anomalies:
        limitations.append("Khong tim thay giao dich bat thuong trong pham vi hien tai.")
    return {
        "anomalies": anomalies,
        "summary": summary,
        "data_source": "bank_simulator",
        "limitations": limitations,
    }


def explain_anomaly_for_chat(user_id: str, anomaly_id: str) -> dict[str, Any]:
    from spectra.web import server

    safe_id = str(anomaly_id or "").strip()
    if not safe_id:
        return {"found": False, "message": "Missing anomaly_id."}

    with server._get_db() as db:
        row = db._conn.execute(
            """
            SELECT id, created_at, merchant, amount, category, anomaly_reason
            FROM bank_transactions
            WHERE user_id = ? AND id = ? AND is_anomaly = TRUE
            LIMIT 1
            """,
            (user_id, safe_id),
        ).fetchone()

    if not row:
        return {"found": False, "message": "Khong tim thay anomaly nay cho nguoi dung hien tai."}

    anomaly = _normalize_bank_anomaly(row)
    return {
        "found": True,
        "anomaly": anomaly,
        "explanation": {
            "why_unusual": anomaly["reason"] or "Giao dich nay duoc danh dau la bat thuong so voi hanh vi chi tieu thong thuong.",
            "what_to_check": [
                "Kiem tra day co phai chi tieu that khong.",
                "Kiem tra co bi trung giao dich khong.",
                "Neu dung la chi tieu that, can nhac dua vao ngan sach theo doi trong ky nay.",
            ],
        },
    }


def get_balance_forecast_for_chat(user_id: str) -> dict[str, Any]:
    from spectra.web import server

    with server._get_db() as db:
        balance_row = db._conn.execute(
            "SELECT balance FROM bank_accounts WHERE user_id = ? LIMIT 1",
            (user_id,),
        ).fetchone()
        if not balance_row:
            return {
                "available": False,
                "message": "Hien tai minh chua truy cap duoc du lieu ngan hang gia lap cua ban. Ban hay ket noi Bank Simulator truoc roi thu lai.",
                "data_source": "bank_simulator",
                "limitations": ["Khong tim thay tai khoan Bank Simulator cho user hien tai."],
            }

        current_balance = float(balance_row[0] or 0)
        spending_row = db._conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) / 30.0, COUNT(*)
            FROM bank_transactions
            WHERE user_id = ?
                AND transaction_type = 'debit'
                AND created_at >= NOW() - INTERVAL '30 days'
            """,
            (user_id,),
        ).fetchone()
        trend_row = db._conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN created_at >= NOW() - INTERVAL '15 days' THEN amount ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN created_at < NOW() - INTERVAL '15 days' AND created_at >= NOW() - INTERVAL '30 days' THEN amount ELSE 0 END), 0)
            FROM bank_transactions
            WHERE user_id = ? AND transaction_type = 'debit'
            """,
            (user_id,),
        ).fetchone()

    avg_daily_spending = float(spending_row[0] or 0) if spending_row else 0.0
    recent_spending = float(trend_row[0] or 0) if trend_row else 0.0
    previous_spending = float(trend_row[1] or 0) if trend_row else 0.0
    spending_trend = _spending_trend(recent_spending, previous_spending)
    today = date.today()
    next_month = today.replace(day=28) + timedelta(days=4)
    last_day = next_month.replace(day=1) - timedelta(days=1)
    days_remaining = max((last_day - today).days, 0)
    predicted_balance = current_balance - (avg_daily_spending * days_remaining)

    return {
        "available": True,
        "current_balance": round(current_balance, 2),
        "predicted_end_of_month_balance": round(predicted_balance, 2),
        "avg_daily_spending": round(avg_daily_spending, 2),
        "days_remaining": days_remaining,
        "spending_trend": spending_trend,
        "recommendation": _forecast_recommendation(current_balance, predicted_balance, spending_trend),
        "data_source": "bank_simulator",
        "limitations": [
            "Du bao dua tren du lieu giao dich hien co va co the thay doi neu phat sinh khoan chi lon hoac thu nhap moi."
        ],
    }


def _normalize_bank_anomaly(row: tuple[Any, ...]) -> dict[str, Any]:
    anomaly_id, created_at, merchant, amount, category, reason = row
    amount_value = float(amount or 0)
    return {
        "id": str(anomaly_id),
        "date": _date_str(created_at),
        "merchant": str(merchant or ""),
        "amount": amount_value,
        "category": str(category or ""),
        "severity": _severity(amount_value),
        "reason": _summarize_reason(str(reason or "")),
    }


def _scope_start_date(scope: str) -> date | None:
    normalized = str(scope or "cycle").strip().lower()
    today = date.today()
    if normalized == "30d":
        return today - timedelta(days=30)
    if normalized == "90d":
        return today - timedelta(days=90)
    if normalized == "cycle":
        return today.replace(day=1)
    return today.replace(day=1)


def _severity(amount: float) -> str:
    if amount > 10_000_000:
        return "high"
    if amount > 1_000_000:
        return "medium"
    return "low"


def _spending_trend(recent: float, previous: float) -> str:
    if previous <= 0:
        return "stable"
    ratio = recent / previous
    if ratio > 1.1:
        return "increasing"
    if ratio < 0.9:
        return "decreasing"
    return "stable"


def _forecast_recommendation(current_balance: float, predicted_balance: float, trend: str) -> str:
    if predicted_balance < 0:
        return "Canh bao: so du uoc tinh cuoi thang co nguy co am. Nen giam cac khoan chi khong thiet yeu."
    if current_balance > 0 and predicted_balance < current_balance * 0.2:
        return "So du uoc tinh cuoi thang thap. Nen theo doi chi tieu sat hon trong cac ngay con lai."
    if trend == "increasing":
        return "Chi tieu dang tang. Nen kiem soat cac khoan khong thiet yeu."
    return "Toc do chi tieu hien tai tuong doi on dinh."


def _summarize_reason(reason: str) -> str:
    cleaned = " ".join(str(reason or "").split())
    return cleaned[:220]


def _date_str(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = str(value or "")
    return raw[:10]


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
