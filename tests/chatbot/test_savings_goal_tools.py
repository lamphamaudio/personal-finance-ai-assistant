import asyncio

from starlette.requests import Request

from spectra.chat.confirmation import pending_actions
from spectra.chat.executor import ToolExecutor


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": []})


def setup_function():
    pending_actions.clear()


def test_plan_savings_goal_rejects_user_id_argument():
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("plan_savings_goal", {"user_id": "other"}))

    assert result.status == "rejected"


def test_create_update_archive_require_confirmation():
    executor = ToolExecutor(_request(), user_id="user-1")

    create = asyncio.run(
        executor.execute(
            "create_savings_goal",
            {"name": "Goal", "target_amount": 1_000_000, "current_amount": 0, "target_date": "2099-01-01"},
        )
    )
    update = asyncio.run(executor.execute("update_savings_goal", {"goal_id": "goal-1", "name": "New"}))
    archive = asyncio.run(executor.execute("archive_savings_goal", {"goal_id": "goal-1"}))

    assert create.status == "rejected"
    assert update.status == "rejected"
    assert archive.status == "rejected"


def test_create_savings_goal_allows_valid_confirmation(monkeypatch):
    arguments = {"name": "Goal", "target_amount": 1_000_000, "current_amount": 0, "target_date": "2099-01-01"}
    action = pending_actions.create(
        user_id="user-1",
        action_type="create_savings_goal",
        tool_name="create_savings_goal",
        tool_arguments=arguments,
        human_summary="Create goal",
    )
    monkeypatch.setattr(
        ToolExecutor,
        "_create_savings_goal",
        lambda self, args: {
            "ok": True,
            "goal": {"id": "goal-1", "target_amount": args["target_amount"]},
            "plan": {"required_plan": {"required_monthly_saving": 100_000}},
        },
    )
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("create_savings_goal", arguments, confirmation_id=action.confirmation_id))

    assert result.status == "success"
    assert pending_actions.get(action.confirmation_id).status == "confirmed"


def test_get_savings_goals_only_uses_current_user(monkeypatch):
    captured = {}

    def fake_get(self, args):
        captured["user_id"] = self.user_id
        return {"goals": [{"id": "goal-1", "user_id": self.user_id}], "total": 1}

    monkeypatch.setattr(ToolExecutor, "_get_savings_goals", fake_get)
    executor = ToolExecutor(_request(), user_id="user-1")

    result = asyncio.run(executor.execute("get_savings_goals", {"status": "active"}))

    assert result.status == "success"
    assert captured["user_id"] == "user-1"
