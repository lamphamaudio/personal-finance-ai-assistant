import asyncio
from types import SimpleNamespace

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatIntent, ChatRequest, ChatResponse, ChatToolCallTrace, ToolExecutionResult
from spectra.chat.supervisor import ChatSupervisor
from spectra.config import Settings


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def _settings(*, api_key: str = "test-openai-key", finalizer_enabled: bool = True) -> Settings:
    return Settings(ai_provider="local", openai_api_key=api_key, chat_finalizer_enabled=finalizer_enabled)


class _FakeOpenAIClient:
    def __init__(self, content: str | None = None, *, error: Exception | None = None):
        self.content = content
        self.error = error
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


async def _fake_forecast_execute(self, tool_name, arguments=None, **kwargs):
    return ToolExecutionResult(
        tool_name=tool_name,
        status="success",
        data={
            "available": True,
            "current_balance": 18_456_910,
            "predicted_end_of_month_balance": 16_133_331,
            "avg_daily_spending": 250_000,
            "days_remaining": 10,
            "spending_trend": "stable",
        },
    )


def test_finalizer_skips_when_openai_key_is_missing(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_forecast_execute)
    monkeypatch.setattr(
        ChatSupervisor,
        "_make_openai_client",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("OpenAI should not be called"))),
    )
    supervisor = ChatSupervisor(_request(), user_id="user-1", settings=_settings(api_key=""))

    response = asyncio.run(
        supervisor.respond(ChatRequest(message="toi dang co bao tien vay?", debug=True))
    )

    assert "18,456,910" in response.answer
    assert response.debug["finalizer"] == {"used": False, "fallback_reason": "missing_openai_key"}


def test_finalizer_rewrites_read_only_forecast_answer(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_forecast_execute)
    fake_client = _FakeOpenAIClient(
        "Ban dang co 18,456,910 VND. Neu giu toc do chi tieu hien tai, "
        "so du cuoi thang uoc tinh con 16,133,331 VND."
    )
    monkeypatch.setattr(ChatSupervisor, "_make_openai_client", staticmethod(lambda *args, **kwargs: fake_client))
    supervisor = ChatSupervisor(_request(), user_id="user-1", settings=_settings())

    response = asyncio.run(
        supervisor.respond(ChatRequest(message="neu cu an trua the thi den cuoi thang toi con bao tien?", debug=True))
    )

    assert response.answer.startswith("Ban dang co 18,456,910 VND")
    assert "16,133,331 VND" in response.answer
    assert response.tool_calls[0].tool_name == "get_balance_forecast"
    assert response.debug["finalizer"]["used"] is True
    assert fake_client.calls[0]["model"] == "gpt-4o-mini"
    assert "fallback_answer" in fake_client.calls[0]["messages"][1]["content"]


def test_finalizer_falls_back_when_openai_errors(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_forecast_execute)
    fake_client = _FakeOpenAIClient(error=RuntimeError("boom"))
    monkeypatch.setattr(ChatSupervisor, "_make_openai_client", staticmethod(lambda *args, **kwargs: fake_client))
    supervisor = ChatSupervisor(_request(), user_id="user-1", settings=_settings())

    response = asyncio.run(
        supervisor.respond(ChatRequest(message="toi dang co bao tien vay?", debug=True))
    )

    assert "18,456,910" in response.answer
    assert response.debug["finalizer"] == {"used": False, "fallback_reason": "openai_error"}


def test_finalizer_falls_back_when_output_is_sensitive(monkeypatch):
    monkeypatch.setattr(ToolExecutor, "execute", _fake_forecast_execute)
    fake_client = _FakeOpenAIClient("user_id user-1 co account_number 1234567890123456")
    monkeypatch.setattr(ChatSupervisor, "_make_openai_client", staticmethod(lambda *args, **kwargs: fake_client))
    supervisor = ChatSupervisor(_request(), user_id="user-1", settings=_settings())

    response = asyncio.run(
        supervisor.respond(ChatRequest(message="toi dang co bao tien vay?", debug=True))
    )

    assert "18,456,910" in response.answer
    assert response.debug["finalizer"] == {"used": False, "fallback_reason": "unsafe_output"}


def test_finalizer_does_not_run_for_confirmation_or_guardrail(monkeypatch):
    monkeypatch.setattr(
        ChatSupervisor,
        "_make_openai_client",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("OpenAI should not be called"))),
    )
    supervisor = ChatSupervisor(_request(), user_id="user-1", settings=_settings())
    confirmation_response = ChatResponse(
        answer="Ban xac nhan thay doi nay khong?",
        intent=ChatIntent.SAVING_SUGGESTION,
        requires_confirmation=True,
        tool_calls=[
            ChatToolCallTrace(
                tool_name="update_budget_limit",
                arguments={"category": "mua sam", "limit": 2_000_000},
                status="success",
            )
        ],
    )

    confirmation = asyncio.run(
        supervisor._finalize_read_answer(ChatRequest(message="xac nhan?", debug=True), confirmation_response)
    )
    guardrail = asyncio.run(supervisor.respond(ChatRequest(message="Co nen mua co phieu AAPL khong?")))

    assert confirmation.requires_confirmation
    assert confirmation.answer == "Ban xac nhan thay doi nay khong?"
    assert guardrail.intent == "OUT_OF_SCOPE_INVESTMENT_ADVICE"
