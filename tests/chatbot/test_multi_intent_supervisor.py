import asyncio
import json

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest, ToolExecutionResult
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


_COMPOUND = (
    "6 tháng gần nhất tôi chi tiêu bao nhiêu, và với lương 18tr thì 5 năm tôi muốn "
    "để dành 500tr thì mỗi tháng cần đưa bao nhiêu vào tài khoản?"
)


# ── _is_multi_intent heuristic ──────────────────────────────────────────────


def test_is_multi_intent_true_for_compound_question():
    assert ChatSupervisor._is_multi_intent(_COMPOUND, ChatSupervisor._fold(_COMPOUND))


def test_is_multi_intent_false_for_single_average_question():
    msg = "Trung bình chi tiêu 6 tháng gần đây là bao nhiêu"
    assert not ChatSupervisor._is_multi_intent(msg, ChatSupervisor._fold(msg))


def test_is_multi_intent_false_for_single_summary_with_conjunction():
    # "tổng chi và thu" is a single summary intent even though it has "và".
    msg = "tổng chi và thu trong tháng 5 là bao nhiêu?"
    assert not ChatSupervisor._is_multi_intent(msg, ChatSupervisor._fold(msg))


def test_is_multi_intent_true_for_two_question_marks():
    msg = "Tháng này tôi tiêu bao nhiêu? Quỹ khẩn cấp của tôi đủ mấy tháng?"
    assert ChatSupervisor._is_multi_intent(msg, ChatSupervisor._fold(msg))


# ── fast-path must not short-circuit a compound question ────────────────────


def test_fast_path_skips_deterministic_for_compound(monkeypatch):
    supervisor = ChatSupervisor(_request(), "user-1")

    async def boom(*args, **kwargs):
        raise AssertionError("deterministic read flow must be skipped for compound questions")

    monkeypatch.setattr(ChatSupervisor, "_handle_phase4_read_flow", boom)

    state = {
        "message": _COMPOUND,
        "session_id": None,
        "scope": "cycle",
        "debug": False,
        "confirmation_id": None,
        "confirm": None,
    }
    result = asyncio.run(supervisor._fast_path_node(state))
    assert result == {"execution_plan": None}
    assert "response" not in result


# ── end-to-end: planner decomposes, executor runs both, synthesis combines ──


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, handler):
        self._handler = handler

    def create(self, **kwargs):
        return _FakeResponse(self._handler(kwargs))


class _FakeChat:
    def __init__(self, handler):
        self.completions = _FakeCompletions(handler)


class _FakeClient:
    def __init__(self, handler):
        self.chat = _FakeChat(handler)


def test_compound_question_decomposes_and_synthesizes(monkeypatch):
    llm_calls = []

    def handler(kwargs):
        system = kwargs["messages"][0]["content"]
        # Capture full serialised messages so assertions can inspect any role/content.
        llm_calls.append(json.dumps(kwargs["messages"], ensure_ascii=False))
        if "SYNTHESIS RULES" in system:
            return (
                "Trong 6 tháng gần đây bạn chi 7.500.000 VND. "
                "Để dành 500 triệu trong 5 năm, mỗi tháng cần khoảng 8.333.333 VND."
            )
        if "Execution Plan" in system:
            return json.dumps(
                {
                    "thought": "tach 2 y",
                    "plan": [
                        {
                            "id": "1",
                            "tool_name": "get_account_summary",
                            "arguments": {"date_from": "2026-01-01", "date_to": "2026-07-01"},
                            "depends_on": [],
                            "requires_confirmation": False,
                        },
                        {
                            "id": "2",
                            "tool_name": "plan_savings_goal",
                            "arguments": {
                                "name": "Muc tieu",
                                "target_amount": 500000000,
                                "current_amount": 0,
                                "target_date": "2031-06-01",
                            },
                            "depends_on": [],
                            "requires_confirmation": False,
                        },
                    ],
                    "direct_response": None,
                }
            )
        return "FINALIZER_SHOULD_NOT_RUN"

    monkeypatch.setattr(ChatSupervisor, "_make_openai_client", staticmethod(lambda *a, **k: _FakeClient(handler)))

    async def fake_execute(self, tool_name, arguments=None, **kwargs):
        data = {
            "get_account_summary": {"has_data": True, "total_spent": 7_500_000, "currency": "VND"},
            "plan_savings_goal": {"required_monthly": 8_333_333, "currency": "VND"},
        }[tool_name]
        return ToolExecutionResult(tool_name=tool_name, status="success", data=data)

    monkeypatch.setattr(ToolExecutor, "execute", fake_execute)

    supervisor = ChatSupervisor(_request(), "user-1")
    monkeypatch.setattr(supervisor.settings, "openai_api_key", "test-key")

    response = asyncio.run(supervisor.respond(ChatRequest(message=_COMPOUND)))

    # Both sub-questions were answered in one synthesized response.
    assert "7.500.000" in response.answer
    assert "8.333.333" in response.answer

    # Both tools were planned and executed.
    executed = {tc.tool_name for tc in response.tool_calls}
    assert executed == {"get_account_summary", "plan_savings_goal"}

    # Exactly two LLM calls: planner + synthesis. The finalizer rewrite is skipped.
    assert len(llm_calls) == 2
    assert any("Execution Plan" in c for c in llm_calls)
    assert any("SYNTHESIS RULES" in c for c in llm_calls)
    # Synthesis received both tool results.
    synthesis_prompt = next(c for c in llm_calls if "SYNTHESIS RULES" in c)
    assert "get_account_summary" in synthesis_prompt
    assert "plan_savings_goal" in synthesis_prompt
