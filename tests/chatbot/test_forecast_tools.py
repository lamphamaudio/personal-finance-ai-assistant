import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_get_balance_forecast_returns_normalized_fields(monkeypatch):
    from spectra.chat import finance_tools

    def fake_forecast(user_id):
        return {
            "available": True,
            "current_balance": 12000000,
            "predicted_end_of_month_balance": 8500000,
            "avg_daily_spending": 250000,
            "days_remaining": 14,
            "spending_trend": "increasing",
            "recommendation": "Chi tieu dang tang.",
            "data_source": "bank_simulator",
            "limitations": ["Du bao la uoc tinh."],
        }

    monkeypatch.setattr(finance_tools, "get_balance_forecast_for_chat", fake_forecast)
    executor = ToolExecutor(_request(), user_id="real-user")

    result = asyncio.run(executor.execute("get_balance_forecast", {"scope": "current_month", "user_id": "other-user"}))

    assert result.status == "success"
    assert result.data["predicted_end_of_month_balance"] == 8500000
    assert result.data["spending_trend"] == "increasing"
    assert result.data["limitations"]


def test_missing_bank_simulator_data_returns_graceful_error(monkeypatch):
    from spectra.chat import finance_tools

    monkeypatch.setattr(
        finance_tools,
        "get_balance_forecast_for_chat",
        lambda user_id: {
            "available": False,
            "message": "Hien tai minh chua truy cap duoc du lieu ngan hang gia lap cua ban.",
            "data_source": "bank_simulator",
            "limitations": ["missing"],
        },
    )
    executor = ToolExecutor(_request(), user_id="real-user")

    result = asyncio.run(executor.execute("get_balance_forecast", {}))

    assert result.status == "success"
    assert result.data["available"] is False
    assert "ngan hang" in result.data["message"]
