import asyncio

from starlette.requests import Request

from spectra.chat.models import ChatRequest
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_chat_response_schema_has_ui_fields():
    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Xoa het du lieu di")))
    data = response.model_dump(mode="json")

    assert "suggested_actions" in data
    assert "requires_confirmation" in data
    assert "confirmation" in data


def test_debug_trace_hidden_when_debug_false(monkeypatch):
    async def fake_phase4(self, chat_request):
        from spectra.chat.models import ChatResponse, ChatToolCallTrace

        return ChatResponse(
            answer="ok",
            tool_calls=[ChatToolCallTrace(tool_name="get_budget_status", arguments={}, status="success")],
            debug={"secret": "not shown"} if chat_request.debug else None,
        )

    monkeypatch.setattr(ChatSupervisor, "_handle_phase4_read_flow", fake_phase4)
    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="test", debug=False)))

    assert response.debug is None
    assert response.tool_calls[0].tool_name == "get_budget_status"


def test_investment_request_is_refused():
    response = asyncio.run(ChatSupervisor(_request(), "user-1").respond(ChatRequest(message="Toi nen mua coin nao?")))

    assert response.intent == "OUT_OF_SCOPE_INVESTMENT_ADVICE"
    assert not response.tool_calls


def test_reset_db_is_not_registered():
    from spectra.chat.tools import get_registered_tools

    assert "reset_db" not in get_registered_tools()
