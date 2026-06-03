import asyncio
from datetime import UTC, datetime, timedelta

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_unknown_confirmation_id_is_rejected():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(
        executor.execute(
            "update_transaction_category",
            {"tx_id": "tx-1", "category": "Food", "apply_to_future": False},
            confirmation_id="confirm_missing",
        )
    )

    assert result.status == "rejected"
    assert "Unknown" in (result.error or "")


def test_expired_confirmation_id_is_rejected():
    action = pending_actions.create(
        user_id="user-1",
        action_type="update_transaction_category",
        tool_name="update_transaction_category",
        tool_arguments={"tx_id": "tx-1", "category": "Food", "apply_to_future": False},
        human_summary="Update tx",
    )
    action.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute(action.tool_name, action.tool_arguments, confirmation_id=action.confirmation_id))

    assert result.status == "rejected"
    assert "expired" in (result.error or "")


def test_confirmation_id_for_another_user_is_rejected():
    action = pending_actions.create(
        user_id="user-1",
        action_type="update_transaction_category",
        tool_name="update_transaction_category",
        tool_arguments={"tx_id": "tx-1", "category": "Food", "apply_to_future": False},
        human_summary="Update tx",
    )
    executor = ToolExecutor(_request(), user_id="user-2")

    result = asyncio.run(executor.execute(action.tool_name, action.tool_arguments, confirmation_id=action.confirmation_id))

    assert result.status == "rejected"
    assert "user" in (result.error or "").lower()
