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


def test_chatbot_does_not_create_memory_rule_automatically_after_update(monkeypatch):
    arguments = {"tx_id": "tx-1", "category": "Food", "apply_to_future": False}
    action = pending_actions.create(
        user_id="user-1",
        action_type="update_transaction_category",
        tool_name="update_transaction_category",
        tool_arguments=arguments,
        human_summary="Update tx",
    )
    calls = []

    def fake_update(self, args):
        calls.append("update")
        return {"ok": True, "id": "tx-1", "merchant": "Highlands", "category": "Food"}

    def fake_create_rule(self, args):
        calls.append("create_rule")
        return {"ok": True, "rule": args}

    monkeypatch.setattr(ToolExecutor, "_update_transaction_category", fake_update)
    monkeypatch.setattr(ToolExecutor, "_create_category_rule", fake_create_rule)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = asyncio.run(
        supervisor.respond(ChatRequest(message="Dong y", confirmation_id=action.confirmation_id, confirm=True))
    )

    assert response.tool_calls[0].tool_name == "update_transaction_category"
    assert calls == ["update"]
    assert "ghi nho" in response.answer.lower()
