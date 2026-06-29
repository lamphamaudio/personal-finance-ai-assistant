"""Tests for the clarification / suggestion flow.

When the user asks without enough information, the bot should ask a short clarifying
question plus clickable suggestion chips instead of guessing or returning a raw error.

Three layers are covered:
- Layer 1 (planner): the planner emits a `clarification` object -> CLARIFICATION_NEEDED.
- Layer 2 (reactive): a planning tool reports blocking `missing_data` (income/budget_limits).
- Layer 3 (defensive): a tool is rejected for a missing required argument.
"""

import asyncio
import json

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatIntent, ChatRequest, ChatToolCallTrace
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


# ── fake OpenAI client (planner returns canned JSON) ────────────────────────


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


def _supervisor(monkeypatch) -> ChatSupervisor:
    sv = ChatSupervisor(_request(), "user-1")
    monkeypatch.setattr(sv.settings, "openai_api_key", "test-key")
    return sv


def _set_planner(monkeypatch, payload: dict) -> None:
    content = json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(
        ChatSupervisor,
        "_make_openai_client",
        staticmethod(lambda *a, **k: _FakeClient(lambda kwargs: content)),
    )


def _planner_state(message: str) -> dict:
    return {
        "message": message,
        "session_id": None,
        "scope": "cycle",
        "debug": False,
        "execution_plan": None,
    }


def _synth_state(tool_name, data, message, *, status="success", error=None) -> dict:
    task = {
        "id": "1",
        "tool_name": tool_name,
        "arguments": {},
        "depends_on": [],
        "requires_confirmation": False,
    }
    result = {"tool_name": tool_name, "status": status, "data": data, "error": error}
    trace = ChatToolCallTrace(tool_name=tool_name, arguments={}, status=status, error=error)
    return {
        "execution_plan": [task],
        "tool_results": [result],
        "tool_calls": [trace],
        "message": message,
        "debug": False,
        "response": None,
        "synthesized_by_llm": False,
    }


# ── Layer 1: planner clarification ──────────────────────────────────────────


def test_planner_vague_request_returns_clarification(monkeypatch):
    sv = _supervisor(monkeypatch)
    _set_planner(
        monkeypatch,
        {
            "thought": "yeu cau mo ho",
            "plan": [],
            "direct_response": None,
            "clarification": {
                "question": "Bạn muốn mình giúp mảng nào?",
                "suggestions": [
                    {"label": "Xem tổng quan chi tiêu", "message": "xem tổng quan chi tiêu của tôi"},
                    {"label": "Đánh giá sức khỏe tài chính", "message": "đánh giá sức khỏe tài chính của tôi"},
                ],
            },
        },
    )

    out = asyncio.run(sv._planner_node(_planner_state("giúp tôi quản lý tài chính")))

    assert out["early_return"] is True
    assert out["execution_plan"] == []
    resp = out["response"]
    assert resp.intent == ChatIntent.CLARIFICATION_NEEDED
    assert resp.answer == "Bạn muốn mình giúp mảng nào?"
    assert len(resp.suggested_actions) == 2
    for action in resp.suggested_actions:
        assert action.type == "prompt"
        assert action.arguments["message"]


def test_planner_missing_required_argument_returns_clarification(monkeypatch):
    sv = _supervisor(monkeypatch)
    _set_planner(
        monkeypatch,
        {
            "thought": "thieu so tien va thoi han",
            "plan": [],
            "direct_response": None,
            "clarification": {
                "question": "Bạn muốn tiết kiệm bao nhiêu và trong bao lâu?",
                "suggestions": [
                    {"label": "20 triệu trong 6 tháng", "message": "tiết kiệm 20 triệu trong 6 tháng"},
                ],
            },
        },
    )

    out = asyncio.run(sv._planner_node(_planner_state("tạo mục tiêu tiết kiệm cho tôi")))

    resp = out["response"]
    assert resp.intent == ChatIntent.CLARIFICATION_NEEDED
    assert "bao nhiêu" in resp.answer
    assert len(resp.suggested_actions) == 1


def test_planner_clarification_ignored_when_confirmation_present(monkeypatch):
    # A write plan must go through the confirmation flow, never clarification.
    sv = _supervisor(monkeypatch)
    _set_planner(
        monkeypatch,
        {
            "thought": "x",
            "direct_response": None,
            "plan": [
                {
                    "id": "1",
                    "tool_name": "create_savings_goal",
                    "arguments": {
                        "name": "Quỹ",
                        "target_amount": 1000000,
                        "current_amount": 0,
                        "target_date": "2030-01-01",
                    },
                    "depends_on": [],
                    "requires_confirmation": True,
                }
            ],
            "clarification": {"question": "?", "suggestions": []},
        },
    )

    out = asyncio.run(sv._planner_node(_planner_state("tạo mục tiêu tiết kiệm 1 triệu")))

    assert "response" not in out
    assert out["execution_plan"][0]["tool_name"] == "create_savings_goal"


def test_respond_vague_propagates_suggested_actions(monkeypatch):
    # End-to-end: the clarification must survive routing + output guard and reach the caller.
    sv = _supervisor(monkeypatch)
    _set_planner(
        monkeypatch,
        {
            "thought": "mo ho",
            "plan": [],
            "direct_response": None,
            "clarification": {
                "question": "Bạn muốn mình giúp mảng nào?",
                "suggestions": [
                    {"label": "Xem tổng quan chi tiêu", "message": "xem tổng quan chi tiêu"},
                    {"label": "Lập kế hoạch ngân sách", "message": "lập kế hoạch ngân sách"},
                ],
            },
        },
    )

    # Force the message past the deterministic / fast-path handlers to the planner.
    monkeypatch.setattr(ChatSupervisor, "_handle_phase3_category_flow", lambda self, req: None)

    async def _none(self, *a, **k):
        return None

    monkeypatch.setattr(ChatSupervisor, "_handle_phase4_read_flow", _none)
    monkeypatch.setattr(ChatSupervisor, "_handle_phase7_budget_flow", _none)

    resp = asyncio.run(sv.respond(ChatRequest(message="bạn có thể giúp tôi điều gì về tài chính")))

    assert resp.intent == ChatIntent.CLARIFICATION_NEEDED
    assert len(resp.suggested_actions) == 2
    assert resp.suggested_actions[0].arguments["message"] == "xem tổng quan chi tiêu"
    assert resp.tool_calls == []


# ── Layer 2: reactive missing_data ──────────────────────────────────────────


def test_synthesis_missing_income_asks_clarification(monkeypatch):
    sv = _supervisor(monkeypatch)
    state = _synth_state(
        "recommend_budget_plan",
        {"missing_data": ["income"], "recommended_budgets": []},
        "lập kế hoạch ngân sách giúp tôi",
    )

    out = asyncio.run(sv._synthesis_node(state))

    resp = out["response"]
    assert resp.intent == ChatIntent.CLARIFICATION_NEEDED
    assert "thu nhập" in resp.answer.lower()
    labels = [a.label for a in resp.suggested_actions]
    assert any("Ước lượng" in label for label in labels)
    assert resp.tool_calls  # the attempted tool call is preserved


def test_synthesis_missing_budget_limits_asks_clarification(monkeypatch):
    sv = _supervisor(monkeypatch)
    state = _synth_state(
        "get_budget_status",
        {"missing_data": ["budget_limits"], "categories": []},
        "tình hình ngân sách của tôi",
    )

    out = asyncio.run(sv._synthesis_node(state))

    resp = out["response"]
    assert resp.intent == ChatIntent.CLARIFICATION_NEEDED
    assert "hạn mức" in resp.answer.lower()
    assert resp.suggested_actions


def test_clarification_for_missing_data_passthrough(monkeypatch):
    sv = _supervisor(monkeypatch)
    # No blocking gap -> normal formatting should run (None).
    assert sv._clarification_for_missing_data("recommend_budget_plan", {"missing_data": []}, "m") is None
    # Non-planning tool is never intercepted.
    assert sv._clarification_for_missing_data("get_account_summary", {"missing_data": ["income"]}, "m") is None


# ── Layer 3: defensive rejected tool ────────────────────────────────────────


def test_synthesis_rejected_missing_field_asks_clarification(monkeypatch):
    sv = _supervisor(monkeypatch)
    state = _synth_state(
        "plan_savings_goal",
        None,
        "lên kế hoạch tiết kiệm",
        status="rejected",
        error="Input validation failed: 'target_amount' is a required property",
    )

    out = asyncio.run(sv._synthesis_node(state))

    resp = out["response"]
    assert resp.intent == ChatIntent.CLARIFICATION_NEEDED
    assert "target_amount" in resp.answer
    assert "Input validation failed" not in resp.answer


def test_missing_required_field_parser():
    assert (
        ChatSupervisor._missing_required_field(
            "Input validation failed: 'target_amount' is a required property"
        )
        == "target_amount"
    )
    assert ChatSupervisor._missing_required_field("some other error") is None
    assert ChatSupervisor._missing_required_field(None) is None
