import asyncio

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_supervisor_routes_savings_plan_question(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "goal": {"target_amount": 20_000_000, "currency": "VND", "target_date": "2099-01-01"},
                "required_plan": {"required_monthly_saving": 3_333_333},
                "feasibility": {"label": "challenging", "reason": "Co the dat neu giu ky luat."},
                "recommended_adjustments": [],
                "next_actions": ["Kiem tra tien do sau 30 ngay."],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="Toi muon tiet kiem 20 trieu trong 6 thang thi lam sao?")))

    assert response.intent == "SAVING_SUGGESTION"
    assert response.tool_calls[0].tool_name == "plan_savings_goal"
    assert "3,333,333" in response.answer
    assert "ước tính" in response.answer
    assert "Để tiết kiệm" in response.answer
    assert "Bước tiếp theo" in response.answer


def test_supervisor_does_not_create_goal_from_first_request(monkeypatch):
    calls = []

    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        calls.append(tool_name)
        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "goal": {"target_amount": 20_000_000, "currency": "VND", "target_date": "2099-01-01"},
                "required_plan": {"required_monthly_saving": 3_333_333},
                "feasibility": {"label": "challenging", "reason": "Co the dat neu giu ky luat."},
                "recommended_adjustments": [],
                "next_actions": [],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(supervisor.respond(ChatRequest(message="Tao cho toi muc tieu tiet kiem 20 trieu trong 6 thang.")))

    assert calls == ["plan_savings_goal"]
    assert not response.requires_confirmation


def test_supervisor_create_that_goal_uses_confirmation_after_plan(monkeypatch):
    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        from spectra.chat.models import ToolExecutionResult

        return ToolExecutionResult(
            tool_name=tool_name,
            status="success",
            data={
                "goal": {"target_amount": 20_000_000, "currency": "VND", "target_date": "2099-01-01"},
                "required_plan": {"required_monthly_saving": 3_333_333},
                "feasibility": {"label": "challenging", "reason": "Co the dat neu giu ky luat."},
                "recommended_adjustments": [],
                "next_actions": [],
            },
        )

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    asyncio.run(supervisor.respond(ChatRequest(message="Toi muon tiet kiem 20 trieu trong 6 thang")))
    response = asyncio.run(supervisor.respond(ChatRequest(message="Tạo mục tiêu đó đi")))

    assert response.requires_confirmation
    assert response.confirmation
    assert response.confirmation.action_type == "create_savings_goal"


def test_fold_preserves_vietnamese_d_letter_for_create_followup():
    normalized = ChatSupervisor._fold("T\u1ea1o m\u1ee5c ti\u00eau \u0111\u00f3 \u0111i")

    assert normalized == "tao muc tieu do di"
    assert ChatSupervisor._is_goal_create_request(normalized)
