import asyncio

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


_SUMMARY = {
    "total_income": 0.0,
    "total_spent": 1_000_000.0,
    "by_category": {"Ăn uống": 1_000_000.0},
    "currency": "VND",
}


def test_recommend_budget_plan_uses_stated_monthly_income():
    from spectra.budget_planner import recommend_budget_plan

    result = recommend_budget_plan(
        "user-1",
        scope="cycle",
        monthly_income=8_000_000,
        summary_payload=_SUMMARY,
        budget_payload={"items": []},
    )
    # Stated salary overrides the (zero) income derived from transactions.
    assert result["summary"]["total_income"] == 8_000_000
    assert result["summary"]["income_source"] == "user_stated"
    assert result["summary"]["available_for_spending"] > 0
    assert "income" not in result["missing_data"]
    # With real income there is room to allocate a non-trivial category budget.
    assert any(item["recommended_budget"] > 0 for item in result["recommended_budgets"])


def test_recommend_budget_plan_falls_back_to_data_income():
    from spectra.budget_planner import recommend_budget_plan

    result = recommend_budget_plan(
        "user-1",
        scope="cycle",
        summary_payload=_SUMMARY,
        budget_payload={"items": []},
    )
    assert result["summary"]["total_income"] == 0
    assert result["summary"]["income_source"] == "transactions"
    assert "income" in result["missing_data"]


def test_recommend_budget_plan_uses_template_when_history_sparse():
    from spectra.budget_planner import recommend_budget_plan

    # One historical category + a stated salary -> a multi-category template plan.
    result = recommend_budget_plan(
        "user-1",
        scope="cycle",
        monthly_income=8_000_000,
        summary_payload=_SUMMARY,
        budget_payload={"items": []},
    )
    assert result["strategy"] == "template_budget"
    cats = [item["category"] for item in result["recommended_budgets"]]
    assert len(cats) >= 5
    assert "Ăn uống" in cats and "Nhà ở" in cats
    available = result["summary"]["available_for_spending"]
    allocated = sum(item["recommended_budget"] for item in result["recommended_budgets"])
    # The template distributes (almost) all of the spend-able amount.
    assert abs(allocated - available) < 1.0


def test_recommend_budget_plan_uses_history_when_rich():
    from spectra.budget_planner import recommend_budget_plan

    rich = {
        "total_income": 10_000_000.0,
        "total_spent": 6_000_000.0,
        "by_category": {
            "Ăn uống": 3_000_000.0,
            "Di chuyển": 1_500_000.0,
            "Mua sắm": 1_000_000.0,
            "Giải trí": 500_000.0,
        },
        "currency": "VND",
    }
    result = recommend_budget_plan(
        "user-1",
        scope="cycle",
        summary_payload=rich,
        budget_payload={"items": []},
    )
    assert result["strategy"] == "goal_aware_budget"


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
