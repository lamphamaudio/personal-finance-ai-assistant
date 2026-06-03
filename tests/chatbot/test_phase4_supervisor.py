import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_supervisor_routes_anomaly_question_to_get_anomalies(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "anomalies": [
                    {
                        "id": "a-1",
                        "date": "2026-06-02",
                        "merchant": "Highlands",
                        "amount": 650000,
                        "category": "Food",
                        "severity": "medium",
                        "reason": "Higher than usual",
                    }
                ],
                "summary": {"total": 1, "high": 0, "medium": 1, "low": 0},
                "limitations": [],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="Co khoan nao bat thuong khong?")))

    assert response.intent == "ANOMALY_EXPLANATION"
    assert response.tool_calls[0].tool_name == "get_anomalies"
    assert "Highlands" in response.answer


def test_supervisor_routes_forecast_question_to_get_balance_forecast(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "available": True,
                "predicted_end_of_month_balance": 8500000,
                "avg_daily_spending": 250000,
                "days_remaining": 14,
                "spending_trend": "increasing",
                "recommendation": "Chi tieu dang tang.",
                "limitations": ["Du bao la uoc tinh."],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="Cuoi thang toi con bao nhieu?")))

    assert response.intent == "FORECAST_BALANCE"
    assert response.tool_calls[0].tool_name == "get_balance_forecast"
    assert "uoc tinh" in response.answer
    assert "8,500,000" in response.answer


def test_supervisor_routes_current_balance_question_to_get_balance_forecast(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "available": True,
                "current_balance": 12_300_000,
                "predicted_end_of_month_balance": 9_800_000,
                "avg_daily_spending": 250000,
                "days_remaining": 10,
                "spending_trend": "stable",
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="toi dang co bao tien vay?")))

    assert response.intent == "FORECAST_BALANCE"
    assert response.tool_calls[0].tool_name == "get_balance_forecast"
    assert "12,300,000" in response.answer
    assert "lich su chat cu" in response.answer


def test_financial_health_score_is_handled_by_phase5(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "score": 70,
                "level": "Trung binh kha",
                "period": {"label": "cycle"},
                "strengths": [],
                "risks": [],
                "recommended_actions": [],
                "missing_data": [],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="Diem suc khoe tai chinh cua toi la bao nhieu?")))

    assert response.intent == "FINANCIAL_HEALTH_SCORE"
    assert response.tool_calls[0].tool_name == "get_financial_health_score"
