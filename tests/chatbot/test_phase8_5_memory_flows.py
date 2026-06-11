import asyncio

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.models import ChatRequest
from spectra.chat import supervisor as supervisor_module
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_create_that_goal_uses_persisted_session_memory(monkeypatch):
    plan = {"name": "Tiet kiem 20 trieu", "target_amount": 20_000_000, "target_date": "2099-01-01"}

    def fake_get_state(user_id, session_id, memory_type):
        return plan if memory_type == "last_goal_plan" else None

    monkeypatch.setattr(supervisor_module, "get_session_state", fake_get_state)

    response = asyncio.run(
        ChatSupervisor(_request(), "user-1", session_id="chat-1").respond(ChatRequest(message="Tao muc tieu do di"))
    )

    assert response.requires_confirmation
    assert response.confirmation
    assert response.confirmation.action_type == "create_savings_goal"


def test_candidate_number_uses_persisted_transaction_candidates(monkeypatch):
    candidates = {
        "category": "Di chuyen",
        "transactions": [
            {"id": "tx-1", "date": "2026-01-01", "merchant": "Grab", "amount": -50000, "category": "Khac"},
            {"id": "tx-2", "date": "2026-01-02", "merchant": "Grab", "amount": -70000, "category": "Khac"},
        ],
    }

    def fake_get_state(user_id, session_id, memory_type):
        return candidates if memory_type == "last_transaction_candidates" else None

    monkeypatch.setattr(supervisor_module, "get_session_state", fake_get_state)

    response = asyncio.run(ChatSupervisor(_request(), "user-1", session_id="chat-1").respond(ChatRequest(message="Cai thu 2")))

    assert response.requires_confirmation
    assert response.confirmation
    assert "Grab" in response.answer
    assert "70,000" in response.answer


def test_preference_memory_write_requires_confirmation(monkeypatch):
    saved = {}

    def fake_save_state(user_id, session_id, memory_type, value):
        saved[memory_type] = value
        return {"id": "mem-1"}

    monkeypatch.setattr(supervisor_module, "save_session_state", fake_save_state)

    response = asyncio.run(
        ChatSupervisor(_request(), "user-1", session_id="chat-1").respond(
            ChatRequest(message="Lan sau tra loi ngan gon hon nhe")
        )
    )

    assert not response.requires_confirmation
    assert response.memory_updates[0]["status"] == "pending_confirmation"
    assert saved["conversation_summary"]["pending_preference"]["key"] == "response_style"


def test_preference_affirmation_saves_after_user_confirmation(monkeypatch):
    candidate = {
        "memory_type": "preference",
        "key": "response_style",
        "value": {"preference": "shorter_answers"},
        "reason": "User confirmed shorter answers.",
    }

    def fake_get_state(user_id, session_id, memory_type):
        return {"pending_preference": candidate} if memory_type == "conversation_summary" else None

    def fake_upsert(**kwargs):
        assert kwargs["key"] == "response_style"
        return {"id": "mem-1", "key": "response_style"}

    monkeypatch.setattr(supervisor_module, "get_session_state", fake_get_state)
    monkeypatch.setattr(supervisor_module, "upsert_user_memory", fake_upsert)

    response = asyncio.run(ChatSupervisor(_request(), "user-pref", session_id="chat-1").respond(ChatRequest(message="Co")))

    assert not response.requires_confirmation
    assert response.memory_updates[0]["status"] == "saved"


def test_forget_memory_requires_confirmation():
    chat_context = {
        "safe_user_memories": [
            {"id": "mem-1", "memory_type": "preference", "key": "response_style", "value": {"preference": "shorter_answers"}}
        ]
    }

    response = asyncio.run(
        ChatSupervisor(_request(), "user-1", session_id="chat-1", chat_context=chat_context).respond(
            ChatRequest(message="Quen viec toi thich tra loi ngan gon di")
        )
    )

    assert response.requires_confirmation
    assert response.confirmation
    assert response.confirmation.action_type == "forget_user_memory"
