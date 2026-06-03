import asyncio

from starlette.requests import Request

from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def test_tool_executor_rejects_unknown_tool():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("unknown_tool", {}))

    assert result.status == "rejected"


def test_tool_executor_rejects_write_or_destructive_tool_name():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("reset_db", {}))

    assert result.status == "rejected"


def test_get_transactions_defaults_to_safe_pagination(monkeypatch):
    from spectra.web import server

    captured = {}

    def fake_api_transactions(request, page, per_page, category, uncategorized_only, search, date_from, date_to):
        captured.update({"page": page, "per_page": per_page})
        return {"transactions": [], "total": 0, "page": page, "per_page": per_page, "pages": 1}

    monkeypatch.setattr(server, "api_transactions", fake_api_transactions)
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_transactions", {"per_page": 200}))

    assert result.status == "success"
    assert captured == {"page": 1, "per_page": 50}
