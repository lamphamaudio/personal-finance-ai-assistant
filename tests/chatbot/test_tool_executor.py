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


def test_get_account_summary_forwards_explicit_date_range(monkeypatch):
    from spectra.web import server

    captured = {}

    def fake_api_summary(request, scope="cycle", date_from="", date_to=""):
        captured.update({"scope": scope, "date_from": date_from, "date_to": date_to})
        return {"total_spent": 0, "total_income": 0}

    monkeypatch.setattr(server, "api_summary", fake_api_summary)
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(
        executor.execute(
            "get_account_summary",
            {"scope": "cycle", "date_from": "2026-05-01", "date_to": "2026-06-01"},
        )
    )

    assert result.status == "success"
    assert captured == {"scope": "cycle", "date_from": "2026-05-01", "date_to": "2026-06-01"}


def test_insight_tools_reject_user_id_argument():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_recurring_transactions", {"user_id": "other"}))

    assert result.status == "rejected"


def test_recurring_tool_clamps_limit(monkeypatch):
    from spectra.chat import insight_tools

    captured = {}

    def fake_recurring(user_id, *, scope="cycle", limit=10):
        captured.update({"user_id": user_id, "scope": scope, "limit": limit})
        return {"items": [], "summary": {}}

    monkeypatch.setattr(insight_tools, "get_recurring_transactions", fake_recurring)
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_recurring_transactions", {"limit": 500}))

    assert result.status == "success"
    assert captured["limit"] == 20


def test_cashflow_calendar_clamps_days(monkeypatch):
    from spectra.chat import insight_tools

    captured = {}

    def fake_calendar(user_id, *, days=30, forecast_payload=None):
        captured.update({"user_id": user_id, "days": days, "forecast_payload": forecast_payload})
        return {"checkpoints": []}

    monkeypatch.setattr(insight_tools, "get_cashflow_calendar", fake_calendar)
    monkeypatch.setattr(ToolExecutor, "_get_balance_forecast", lambda self, arguments: {"current_balance": 0})
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_cashflow_calendar", {"days": 500}))

    assert result.status == "success"
    assert captured["days"] == 45
