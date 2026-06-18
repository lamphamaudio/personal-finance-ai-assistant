import asyncio
import json
import logging
import sqlite3
import pytest
from starlette.requests import Request

from spectra.chat.executor import ToolExecutor, _TOOL_CACHE
from spectra.chat.models import ToolExecutionResult
from spectra.chat.tools import get_tool
from spectra.config import load_settings


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


@pytest.fixture(autouse=True)
def clear_tool_cache():
    """Ensure a clean in-memory cache for each test case."""
    _TOOL_CACHE._cache.clear()


def test_tool_schema_validation_failure():
    """Verify that the tool executor rejects inputs that fail JSON Schema validation."""
    executor = ToolExecutor(_request(), user_id="user-1")

    # per_page must be an integer, passing a string should trigger validation failure
    result = asyncio.run(executor.execute("get_transactions", {"per_page": "ten"}))

    assert result.status == "rejected"
    assert "Input validation failed" in str(result.error)


def test_tool_schema_validation_success(monkeypatch):
    """Verify that valid inputs pass JSON Schema validation."""
    from spectra.web import server
    monkeypatch.setattr(server, "api_categories_options", lambda req: {"options": ["A", "B"]})

    executor = ToolExecutor(_request(), user_id="user-1")
    result = asyncio.run(executor.execute("get_category_options", {}))

    assert result.status == "success"


def test_tool_caching_and_invalidation(monkeypatch):
    """Verify that read-only tools cache results, and write tools invalidate the session cache."""
    # 1. Mock a read-only tool call
    call_count = 0

    def fake_get_categories():
        nonlocal call_count
        call_count += 1
        return {"options": [f"Category-{call_count}"]}

    monkeypatch.setattr(ToolExecutor, "_get_category_options", lambda self: fake_get_categories())

    executor = ToolExecutor(_request(), user_id="user-1")
    session_id = "test-session-cache"

    # Reset cache before test
    _TOOL_CACHE.invalidate_session("user-1", session_id)

    # First execution - should hit database/fake function
    result1 = asyncio.run(executor.execute("get_category_options", {}, session_id=session_id))
    assert result1.status == "success"
    assert call_count == 1
    assert result1.data == {"options": ["Category-1"]}

    # Second execution - should hit cache
    result2 = asyncio.run(executor.execute("get_category_options", {}, session_id=session_id))
    assert result2.status == "success"
    assert call_count == 1  # count should still be 1 (cache hit)
    assert result2.data == {"options": ["Category-1"]}

    # 2. Mock a write tool execution to trigger invalidation
    from spectra.chat.confirmation import pending_actions

    def fake_update_category(args):
        return {"ok": True, "merchant": "Test", "category": "Food"}

    monkeypatch.setattr(ToolExecutor, "_update_transaction_category", lambda self, args: fake_update_category(args))
    monkeypatch.setattr(ToolExecutor, "_validate_category", lambda self, cat: None)

    # Create a valid PendingAction in the confirmation store
    action = pending_actions.create(
        user_id="user-1",
        action_type="update_transaction_category",
        tool_name="update_transaction_category",
        tool_arguments={"tx_id": "tx123", "category": "Food", "apply_to_future": False},
        human_summary="Doi giao dich Test sang Food",
    )

    # Execute write tool
    write_result = asyncio.run(
        executor.execute(
            "update_transaction_category",
            {"tx_id": "tx123", "category": "Food", "apply_to_future": False},
            confirmation_id=action.confirmation_id,
            session_id=session_id,
        )
    )
    assert write_result.status == "success"

    # Third execution (after cache invalidation) - should hit DB/fake function again
    result3 = asyncio.run(executor.execute("get_category_options", {}, session_id=session_id))
    assert result3.status == "success"
    assert call_count == 2  # count should increment (cache was invalidated)
    assert result3.data == {"options": ["Category-2"]}


def test_tool_timeout(monkeypatch):
    """Verify that slow tools trigger timeout exceptions."""
    async def slow_logic():
        await asyncio.sleep(1.0)
        return {"ok": True}

    # Monkeypatch get_current_user to run very slowly
    monkeypatch.setattr(ToolExecutor, "_get_current_user", lambda self: asyncio.run(slow_logic()))

    # Configure short timeout (0.05 seconds)
    settings = load_settings()
    monkeypatch.setattr(settings, "chat_tool_timeout", 0.05)

    executor = ToolExecutor(_request(), user_id="user-1")
    result = asyncio.run(executor.execute("get_current_user", {}))

    assert result.status == "error"
    assert "timed out" in str(result.error)


def test_tool_transient_retry(monkeypatch):
    """Verify that transient database errors trigger automatic retries and eventually succeed."""
    call_count = 0

    def database_unreliable_logic():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise sqlite3.OperationalError("Database is locked")
        return {"options": ["Recovered"]}

    monkeypatch.setattr(ToolExecutor, "_get_category_options", lambda self: database_unreliable_logic())

    executor = ToolExecutor(_request(), user_id="user-1")
    result = asyncio.run(executor.execute("get_category_options", {}))

    assert result.status == "success"
    assert call_count == 3  # Failed twice, succeeded on the third attempt
    assert result.data == {"options": ["Recovered"]}


def test_structured_json_logging(monkeypatch, caplog):
    """Verify that executing a traced operation produces valid JSON structured logging in logs."""
    from spectra.chat.tracing import start_trace

    caplog.set_level(logging.INFO, logger="spectra.chat.tracing")

    async def dummy_run():
        from spectra.chat.tracing import trace_span
        with trace_span("sub_operation", "chain", {"param": 42}) as span_rec:
            span_rec.outputs = {"result": "success"}

    with start_trace(user_id="user-logger", session_id="session-logger", name="test_logger", inputs={"msg": "hello"}):
        asyncio.run(dummy_run())

    # Find the log messages emitted by spectra.chat.tracing
    json_logs = []
    for record in caplog.records:
        if record.name == "spectra.chat.tracing":
            try:
                json_logs.append(json.loads(record.message))
            except json.JSONDecodeError:
                pass

    # We expect at least two logs: one for sub_operation, one for the root test_logger trace
    assert len(json_logs) >= 2

    # Check the sub-operation span log structure
    sub_span = next(log for log in json_logs if log["name"] == "sub_operation")
    assert sub_span["span_type"] == "chain"
    assert sub_span["user_id"] == "user-logger"
    assert sub_span["session_id"] == "session-logger"
    assert sub_span["inputs"] == {"param": 42}
    assert sub_span["outputs"] == {"result": "success"}
    assert "trace_id" in sub_span
    assert "span_id" in sub_span
    assert "parent_span_id" in sub_span
    assert sub_span["latency_ms"] >= 0.0
