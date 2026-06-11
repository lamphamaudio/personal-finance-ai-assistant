import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_supervisor_routes_over_budget_question(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "currency": "VND",
                "summary": {"total_budget": 3_000_000, "total_spent": 3_500_000, "usage_percentage": 116.7},
                "alerts": ["Ăn uống co nguy co vuot ngan sach."],
                "categories": [{"category": "Ăn uống", "actual_spend": 3_500_000, "budget_limit": 3_000_000, "status": "over"}],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Tôi có đang vượt ngân sách không?")))

    assert response.intent == "SAVING_SUGGESTION"
    assert response.tool_calls[0].tool_name == "get_budget_status"
    assert "VND" in response.answer


def test_supervisor_routes_budget_recommendation(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "currency": "VND",
                "summary": {"total_income": 15_000_000, "target_savings": 2_250_000},
                "recommended_budgets": [{"category": "Ăn uống", "recommended_budget": 3_000_000, "difficulty": "medium"}],
                "next_actions": ["Theo doi chi tieu moi tuan."],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Tôi nên chia ngân sách tháng này thế nào?")))

    assert response.tool_calls[0].tool_name == "recommend_budget_plan"
    assert "ap dung" in response.answer


def test_supervisor_budget_update_requires_confirmation():
    response = asyncio.run(
        ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Giảm ngân sách mua sắm xuống 2 triệu."))
    )

    assert response.requires_confirmation
    assert response.confirmation
    assert response.confirmation.action_type == "update_budget_limit"
