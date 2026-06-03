import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/api/chat", "headers": []})


def test_financial_health_tool_rejects_user_id_argument():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_financial_health_score", {"user_id": "other"}))

    assert result.status == "rejected"


def test_financial_health_tool_rejects_refresh_true():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_financial_health_score", {"refresh": True}))

    assert result.status == "rejected"


def test_financial_health_tool_returns_backend_score(monkeypatch):
    from spectra.chat import finance_tools
    from spectra.web import server

    monkeypatch.setattr(
        server,
        "api_summary",
        lambda request, scope="cycle": {
            "total_income": 10_000_000,
            "total_spent": 7_000_000,
            "by_category": {"An uong": 2_000_000, "Di lai": 1_500_000, "Khac": 3_500_000},
            "current_cycle": {"start": "2026-06-01", "end": "2026-07-01", "label": "June 2026"},
        },
    )
    monkeypatch.setattr(server, "api_budget", lambda request: {"items": [{"status": "on_track"}]})
    monkeypatch.setattr(finance_tools, "get_anomalies_for_chat", lambda user_id, limit=10, scope="cycle": {"summary": {"total": 0, "high": 0}, "anomalies": []})
    monkeypatch.setattr(
        finance_tools,
        "get_balance_forecast_for_chat",
        lambda user_id: {
            "available": True,
            "current_balance": 8_000_000,
            "predicted_end_of_month_balance": 6_000_000,
        },
    )
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_financial_health_score", {"scope": "cycle"}))

    assert result.status == "success"
    assert result.data
    assert 0 <= result.data["score"] <= 100
    assert "user_id" not in result.data
