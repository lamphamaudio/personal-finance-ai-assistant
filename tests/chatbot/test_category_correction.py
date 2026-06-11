from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor
from spectra.chat.models import ChatRequest
from spectra.chat.supervisor import ChatSupervisor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_category_correction_with_multiple_matches_asks_user_to_choose(monkeypatch):
    monkeypatch.setattr(
        ToolExecutor,
        "_get_transactions",
        lambda self, args: {
            "transactions": [
                {"id": "1", "date": "2026-06-02", "merchant": "GrabBike", "amount": -100000, "category": "Other"},
                {"id": "2", "date": "2026-06-02", "merchant": "GrabFood", "amount": -98000, "category": "Other"},
            ]
        },
    )
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = supervisor._handle_phase3_category_flow(ChatRequest(message="doi giao dich Grab sang Transport"))

    assert response.requires_confirmation is False
    assert "1." in response.answer
    assert "2." in response.answer


def test_category_correction_selection_creates_confirmation_after_multiple_matches(monkeypatch):
    monkeypatch.setattr(
        ToolExecutor,
        "_get_transactions",
        lambda self, args: {
            "transactions": [
                {"id": "1", "date": "2026-06-02", "merchant": "GrabBike", "amount": -100000, "category": "Other"},
                {"id": "2", "date": "2026-06-02", "merchant": "GrabFood", "amount": -98000, "category": "Other"},
            ]
        },
    )
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    supervisor._handle_phase3_category_flow(ChatRequest(message="doi giao dich Grab sang Transport"))
    response = supervisor._handle_phase3_category_flow(ChatRequest(message="chon 1"))

    assert response.requires_confirmation is True
    assert response.confirmation is not None
    action = pending_actions.get(response.confirmation.confirmation_id)
    assert action.tool_name == "update_transaction_category"
    assert action.tool_arguments["tx_id"] == "1"


def test_category_correction_single_match_creates_pending_confirmation(monkeypatch):
    monkeypatch.setattr(
        ToolExecutor,
        "_get_transactions",
        lambda self, args: {
            "transactions": [
                {"id": "1", "date": "2026-06-02", "merchant": "Highlands", "amount": -65000, "category": "Other"}
            ]
        },
    )
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = supervisor._handle_phase3_category_flow(ChatRequest(message="doi giao dich Highlands sang Food"))

    assert response.requires_confirmation is True
    assert response.confirmation is not None
    action = pending_actions.get(response.confirmation.confirmation_id)
    assert action.tool_name == "update_transaction_category"


def test_category_correction_strips_transaction_prefix_and_normalizes_vietnamese_category(monkeypatch):
    captured = {}

    def fake_get_transactions(self, args):
        captured.update(args)
        return {
            "transactions": [
                {"id": "1", "date": "2026-06-02", "merchant": "Highlands Coffee", "amount": -65000, "category": "Ăn uống"}
            ]
        }

    monkeypatch.setattr(ToolExecutor, "_get_transactions", fake_get_transactions)
    supervisor = ChatSupervisor(_request(), user_id="user-1")

    response = supervisor._handle_phase3_category_flow(ChatRequest(message="doi giao dich Highlands Coffee sang Giải trí"))

    assert captured["search"] == "highlands coffee"
    assert response.confirmation is not None
    action = pending_actions.get(response.confirmation.confirmation_id)
    assert action.tool_arguments["category"] == "Giải trí"
