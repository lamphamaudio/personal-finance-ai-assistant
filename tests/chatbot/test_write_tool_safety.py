import asyncio

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_update_transaction_category_rejects_without_confirmation():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(
        executor.execute("update_transaction_category", {"tx_id": "tx-1", "category": "Food", "apply_to_future": False})
    )

    assert result.status == "rejected"


def test_create_category_rule_rejects_without_confirmation():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(
        executor.execute("create_category_rule", {"rule_type": "contains", "pattern": "Highlands", "category": "Food"})
    )

    assert result.status == "rejected"


def test_update_transaction_category_allows_valid_confirmation(monkeypatch):
    arguments = {"tx_id": "tx-1", "category": "Food", "apply_to_future": False}
    action = pending_actions.create(
        user_id="user-1",
        action_type="update_transaction_category",
        tool_name="update_transaction_category",
        tool_arguments=arguments,
        human_summary="Update tx",
    )
    monkeypatch.setattr(
        ToolExecutor,
        "_update_transaction_category",
        lambda self, args: {"ok": True, "id": args["tx_id"], "merchant": "Highlands", "category": args["category"]},
    )
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute(action.tool_name, arguments, confirmation_id=action.confirmation_id))

    assert result.status == "success"
    assert pending_actions.get(action.confirmation_id).status == "confirmed"


def test_test_category_rule_is_read_only_and_allowed(monkeypatch):
    monkeypatch.setattr(
        ToolExecutor,
        "_test_category_rule",
        lambda self, args: {"ok": True, "matches_sample": True, "impact_count": 0, "examples": []},
    )
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("test_category_rule", {"pattern": "Highlands", "sample_text": "Highlands Coffee"}))

    assert result.status == "success"
