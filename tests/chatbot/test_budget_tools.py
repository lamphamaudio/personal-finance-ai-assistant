import asyncio

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_budget_read_tools_reject_user_id_argument():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_budget_status", {"user_id": "other"}))

    assert result.status == "rejected"


def test_budget_write_tools_require_confirmation():
    executor = ToolExecutor(_request(), user_id="user-1")

    update = asyncio.run(executor.execute("update_budget_limit", {"category": "Ăn uống", "limit": 3_000_000}))
    upsert = asyncio.run(executor.execute("upsert_budget_plan", {"budgets": [{"category": "Ăn uống", "limit": 3_000_000}]}))

    assert update.status == "rejected"
    assert upsert.status == "rejected"


def test_update_budget_limit_allows_valid_confirmation(monkeypatch):
    args = {"category": "Ăn uống", "limit": 3_000_000}
    action = pending_actions.create(
        user_id="user-1",
        action_type="update_budget_limit",
        tool_name="update_budget_limit",
        tool_arguments=args,
        human_summary="Update budget",
    )
    monkeypatch.setattr(ToolExecutor, "_update_budget_limit", lambda self, arguments: {"ok": True, **arguments})
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("update_budget_limit", args, confirmation_id=action.confirmation_id))

    assert result.status == "success"
    assert pending_actions.get(action.confirmation_id).status == "confirmed"


def test_recommend_budget_plan_returns_data(monkeypatch):
    monkeypatch.setattr(
        ToolExecutor,
        "_recommend_budget_plan",
        lambda self, arguments: {"recommended_budgets": [{"category": "Ăn uống", "recommended_budget": 3_000_000}]},
    )
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("recommend_budget_plan", {"scope": "cycle"}))

    assert result.status == "success"
    assert result.data["recommended_budgets"]


def test_update_budget_limit_saves_user_scoped_limit(monkeypatch):
    from spectra import budget_planner
    from spectra.web import server

    captured = {}

    class FakeDb:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return None

        def save_budget_limit(self, category, monthly_limit, user_id=""):
            captured.update({"category": category, "monthly_limit": monthly_limit, "user_id": user_id})

    monkeypatch.setattr(server, "_get_db", lambda: FakeDb())

    result = budget_planner.update_budget_limit("user-budget", category="Ăn uống", limit=3_000_000)

    assert result["ok"] is True
    assert captured == {"category": "Ăn uống", "monthly_limit": 3_000_000.0, "user_id": "user-budget"}
