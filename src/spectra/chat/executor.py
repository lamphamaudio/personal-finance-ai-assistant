"""Permission-aware allowlisted tool executor for the chatbot."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from spectra.chat.audit import log_write_tool_call
from spectra.chat.confirmation import pending_actions
from spectra.chat.models import ToolExecutionResult
from spectra.chat.redaction import mask_account_number, redact_payload
from spectra.chat.tools import get_tool
from spectra.categories import UNCATEGORIZED, normalize_category
from spectra.ml_classifier import build_seed_data


class ToolExecutor:
    def __init__(self, request: Request, user_id: str):
        self.request = request
        self.user_id = str(user_id or "").strip()

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        confirmation_id: str | None = None,
        session_id: str | None = None,
    ) -> ToolExecutionResult:
        arguments = arguments or {}
        tool = get_tool(tool_name)
        if not tool:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Tool is not registered for the chatbot.",
            )
        if tool.dangerous:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Admin and destructive tools are not available to the chatbot.",
            )
        if tool.requires_session and not self.user_id:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Authenticated session is required.",
            )

        if not tool.read_only:
            guard = self._validate_write_confirmation(tool_name, arguments, confirmation_id)
            if guard:
                return guard
        if tool_name in {
            "plan_savings_goal",
            "simulate_savings_adjustment",
            "get_savings_goals",
            "create_savings_goal",
            "update_savings_goal",
            "archive_savings_goal",
            "get_budget_status",
            "recommend_budget_plan",
            "simulate_budget_adjustment",
            "compare_budget_vs_actual",
            "update_budget_limit",
            "upsert_budget_plan",
            "get_conversation_context",
            "get_user_memories",
            "remember_user_preference",
            "forget_user_memory",
        }:
            guard = self._validate_no_user_id(tool_name, arguments)
            if guard:
                return guard
        if tool_name in {"remember_user_preference", "forget_user_memory"}:
            guard = self._validate_memory_arguments(tool_name, arguments)
            if guard:
                return guard
        if tool_name == "get_financial_health_score":
            guard = self._validate_financial_health_arguments(arguments)
            if guard:
                return guard

        try:
            if tool_name == "get_current_user":
                data = self._get_current_user()
            elif tool_name == "get_account_summary":
                data = self._get_account_summary(arguments)
            elif tool_name == "get_transactions":
                data = self._get_transactions(arguments)
            elif tool_name == "get_category_options":
                data = self._get_category_options()
            elif tool_name == "update_transaction_category":
                data = self._update_transaction_category(arguments)
            elif tool_name == "test_category_rule":
                data = self._test_category_rule(arguments)
            elif tool_name == "create_category_rule":
                data = self._create_category_rule(arguments)
            elif tool_name == "get_category_rules":
                data = self._get_category_rules()
            elif tool_name == "get_learning_summary":
                data = self._get_learning_summary()
            elif tool_name == "get_anomalies":
                data = self._get_anomalies(arguments)
            elif tool_name == "get_balance_forecast":
                data = self._get_balance_forecast(arguments)
            elif tool_name == "explain_anomaly":
                data = self._explain_anomaly(arguments)
            elif tool_name == "get_financial_health_score":
                data = self._get_financial_health_score(arguments)
            elif tool_name == "plan_savings_goal":
                data = self._plan_savings_goal(arguments)
            elif tool_name == "simulate_savings_adjustment":
                data = self._simulate_savings_adjustment(arguments)
            elif tool_name == "get_savings_goals":
                data = self._get_savings_goals(arguments)
            elif tool_name == "create_savings_goal":
                data = self._create_savings_goal(arguments)
            elif tool_name == "update_savings_goal":
                data = self._update_savings_goal(arguments)
            elif tool_name == "archive_savings_goal":
                data = self._archive_savings_goal(arguments)
            elif tool_name == "get_budget_status":
                data = self._get_budget_status(arguments)
            elif tool_name == "recommend_budget_plan":
                data = self._recommend_budget_plan(arguments)
            elif tool_name == "simulate_budget_adjustment":
                data = self._simulate_budget_adjustment(arguments)
            elif tool_name == "compare_budget_vs_actual":
                data = self._compare_budget_vs_actual(arguments)
            elif tool_name == "update_budget_limit":
                data = self._update_budget_limit(arguments)
            elif tool_name == "upsert_budget_plan":
                data = self._upsert_budget_plan(arguments)
            elif tool_name == "get_conversation_context":
                data = self._get_conversation_context(arguments)
            elif tool_name == "get_user_memories":
                data = self._get_user_memories(arguments)
            elif tool_name == "remember_user_preference":
                data = self._remember_user_preference(arguments)
            elif tool_name == "forget_user_memory":
                data = self._forget_user_memory(arguments)
            else:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status="rejected",
                    error="Tool is not executable by the chatbot.",
                )
        except Exception:
            if not tool.read_only and confirmation_id:
                log_write_tool_call(
                    user_id=self.user_id,
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    status="error",
                    confirmation_id=confirmation_id,
                    error_message="Tool execution failed.",
                )
            return ToolExecutionResult(
                tool_name=tool_name,
                status="error",
                error="Tool execution failed.",
            )

        if not tool.read_only and confirmation_id:
            pending_actions.mark_confirmed(confirmation_id)
            log_write_tool_call(
                user_id=self.user_id,
                session_id=session_id,
                tool_name=tool_name,
                arguments=arguments,
                status="success",
                confirmation_id=confirmation_id,
            )
        return ToolExecutionResult(tool_name=tool_name, status="success", data=redact_payload(data))

    def _validate_write_confirmation(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        confirmation_id: str | None,
    ) -> ToolExecutionResult | None:
        if not confirmation_id:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Write tool requires a valid pending confirmation.",
            )
        action = pending_actions.get(confirmation_id)
        if not action:
            return ToolExecutionResult(tool_name=tool_name, status="rejected", error="Unknown confirmation_id.")
        if action.user_id != self.user_id:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Confirmation does not belong to this user.",
            )
        if action.status != "pending":
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error=f"Confirmation is {action.status}.",
            )
        if action.tool_name != tool_name or action.tool_arguments != arguments:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Confirmation does not match this tool call.",
            )
        return None

    def _validate_financial_health_arguments(self, arguments: dict[str, Any]) -> ToolExecutionResult | None:
        if guard := self._validate_no_user_id("get_financial_health_score", arguments):
            return guard
        if bool(arguments.get("refresh") or False):
            return ToolExecutionResult(
                tool_name="get_financial_health_score",
                status="rejected",
                error="refresh is not available to chatbot tools.",
            )
        return None

    def _validate_memory_arguments(self, tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult | None:
        from spectra.chat.memory import LONG_TERM_MEMORY_TYPES, has_sensitive_memory_payload

        if has_sensitive_memory_payload(arguments):
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Memory payload contains sensitive data.",
            )
        if tool_name == "remember_user_preference":
            memory_type = str(arguments.get("memory_type") or "preference")
            if memory_type not in LONG_TERM_MEMORY_TYPES:
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status="rejected",
                    error="Only stable long-term preference memory types are supported.",
                )
        return None

    @staticmethod
    def _validate_no_user_id(tool_name: str, arguments: dict[str, Any]) -> ToolExecutionResult | None:
        if "user_id" in arguments:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="user_id is not accepted for this tool.",
            )
        return None

    def _get_current_user(self) -> dict[str, Any]:
        from spectra.web import server

        user = server._fetch_demo_user(self.user_id)
        if not user:
            raise ValueError("Unknown user")
        return {
            "user_id": str(user.get("user_id", "")),
            "persona_type": str(user.get("persona_type", "")),
            "bank_name": str(user.get("bank_name", "")),
            "account_number_masked": mask_account_number(str(user.get("account_number", ""))),
            "current_balance_masked": True,
        }

    def _get_account_summary(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.web import server

        scope = str(arguments.get("scope") or "cycle").strip().lower()
        if scope not in {"cycle", "90d", "ytd"}:
            scope = "cycle"
        result = server.api_summary(self.request, scope=scope)
        return self._jsonable_response(result)

    def _get_transactions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.web import server

        page = self._positive_int(arguments.get("page"), default=1, max_value=10_000)
        per_page = self._positive_int(arguments.get("per_page"), default=20, max_value=50)
        result = server.api_transactions(
            self.request,
            page=page,
            per_page=per_page,
            category=str(arguments.get("category") or ""),
            uncategorized_only=bool(arguments.get("uncategorized_only") or False),
            search=str(arguments.get("search") or ""),
            date_from=str(arguments.get("date_from") or ""),
            date_to=str(arguments.get("date_to") or ""),
        )
        return self._jsonable_response(result)

    def _get_category_options(self) -> dict[str, Any]:
        from spectra.web import server

        result = server.api_categories_options(self.request)
        return self._jsonable_response(result)

    def _update_transaction_category(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.web import server

        tx_id = str(arguments.get("tx_id") or "").strip()
        category = normalize_category(str(arguments.get("category") or "").strip())
        apply_to_future = bool(arguments.get("apply_to_future") or False)
        if not tx_id or category == UNCATEGORIZED:
            raise ValueError("tx_id and category are required")
        self._validate_category(category)
        with server._get_db() as db:
            row = db._conn.execute(
                """
                SELECT clean_name, original_description, category
                FROM app_tx_history
                WHERE tx_id = ? AND user_id = ?
                """,
                (tx_id, self.user_id),
            ).fetchone()
            if not row:
                raise ValueError("Transaction not found")
            merchant, original_description, old_category = row
            db._conn.execute(
                "UPDATE app_tx_history SET category = ? WHERE tx_id = ? AND user_id = ?",
                (category, tx_id, self.user_id),
            )
            db._conn.commit()
            server._persist_learning(
                db,
                tx_id=tx_id,
                original_description=str(original_description or ""),
                clean_name=str(merchant or ""),
                category=category,
                source="chat_category_correction",
                apply_to_future=apply_to_future,
            )
        return {
            "ok": True,
            "id": tx_id,
            "merchant": str(merchant or ""),
            "old_category": str(old_category or ""),
            "category": category,
            "apply_to_future": apply_to_future,
        }

    def _test_category_rule(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.rules import normalize_rule_type
        from spectra.web import server

        rule_type = normalize_rule_type(str(arguments.get("rule_type") or "contains"))
        pattern = str(arguments.get("pattern") or "").strip()
        sample_text = str(arguments.get("sample_text") or "").strip()
        if not pattern:
            raise ValueError("pattern is required")
        with server._get_db() as db:
            preview = server._simulate_rule_impact(db, rule_type=rule_type, pattern=pattern, sample_text=sample_text)
        preview["examples"] = preview.get("examples", [])[:5]
        return {"ok": True, **preview}

    def _create_category_rule(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.rules import normalize_rule_type
        from spectra.web import server

        rule_type = normalize_rule_type(str(arguments.get("rule_type") or "contains"))
        pattern = str(arguments.get("pattern") or "").strip()
        category = normalize_category(str(arguments.get("category") or "").strip())
        if not pattern or category == UNCATEGORIZED:
            raise ValueError("pattern and category are required")
        self._validate_category(category)
        with server._get_db() as db:
            rule = db.add_category_rule(rule_type=rule_type, pattern=pattern, category=category)
        return {"ok": True, "rule": rule}

    def _get_category_rules(self) -> dict[str, Any]:
        from spectra.web import server

        with server._get_db() as db:
            rules = [rule for rule in db.get_category_rules() if rule.get("is_active", True)]
        return {"rules": rules[:50]}

    def _get_learning_summary(self) -> dict[str, Any]:
        from spectra.web import server

        result = server.api_learning_summary()
        data = self._jsonable_response(result)
        data["events"] = data.get("events", [])[:10]
        return data

    def _get_anomalies(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.finance_tools import get_anomalies_for_chat

        limit = self._positive_int(arguments.get("limit"), default=10, max_value=20)
        scope = str(arguments.get("scope") or "cycle").strip().lower()
        if scope not in {"cycle", "30d", "90d"}:
            scope = "cycle"
        return get_anomalies_for_chat(self.user_id, limit=limit, scope=scope)

    def _get_balance_forecast(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.finance_tools import get_balance_forecast_for_chat

        return get_balance_forecast_for_chat(self.user_id)

    def _explain_anomaly(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.finance_tools import explain_anomaly_for_chat

        return explain_anomaly_for_chat(self.user_id, str(arguments.get("anomaly_id") or ""))

    def _get_financial_health_score(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.finance_tools import get_anomalies_for_chat, get_balance_forecast_for_chat
        from spectra.financial_health import calculate_financial_health_score
        from spectra.web import server

        scope = str(arguments.get("scope") or "cycle").strip().lower()
        if scope not in {"cycle", "90d", "ytd"}:
            scope = "cycle"
        month = str(arguments.get("month") or "").strip() or None

        summary = self._jsonable_response(server.api_summary(self.request, scope=scope))
        budget = self._jsonable_response(server.api_budget(self.request))
        anomaly_scope = "90d" if scope in {"90d", "ytd"} else "cycle"
        anomalies = get_anomalies_for_chat(self.user_id, limit=10, scope=anomaly_scope)
        forecast = get_balance_forecast_for_chat(self.user_id)
        return calculate_financial_health_score(
            self.user_id,
            scope=scope,
            month=month,
            summary_payload=summary,
            anomaly_payload=anomalies,
            forecast_payload=forecast,
            budget_payload=budget,
        )

    def _savings_context(self) -> dict[str, Any]:
        from spectra.chat.finance_tools import get_balance_forecast_for_chat
        from spectra.web import server

        summary = self._jsonable_response(server.api_summary(self.request, scope="cycle"))
        forecast = get_balance_forecast_for_chat(self.user_id)
        return {
            "total_income": summary.get("total_income"),
            "total_spent": summary.get("total_spent"),
            "average_monthly_income": summary.get("total_income"),
            "average_monthly_expense": summary.get("total_spent"),
            "available_monthly_cashflow": float(summary.get("total_income") or 0) - float(summary.get("total_spent") or 0),
            "by_category": summary.get("by_category") or {},
            "forecasted_end_balance": forecast.get("predicted_end_of_month_balance"),
        }

    def _plan_savings_goal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.savings_goals import plan_savings_goal

        return plan_savings_goal(
            self.user_id,
            name=str(arguments.get("name") or ""),
            target_amount=arguments.get("target_amount"),
            current_amount=arguments.get("current_amount") or 0,
            target_date=str(arguments.get("target_date") or ""),
            currency=str(arguments.get("currency") or "VND"),
            context=self._savings_context(),
        )

    def _simulate_savings_adjustment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.savings_goals import simulate_savings_adjustment

        return simulate_savings_adjustment(
            self.user_id,
            target_amount=arguments.get("target_amount"),
            current_amount=arguments.get("current_amount") or 0,
            target_date=str(arguments.get("target_date") or ""),
            adjustments=list(arguments.get("adjustments") or []),
            currency=str(arguments.get("currency") or "VND"),
            context=self._savings_context(),
        )

    def _get_savings_goals(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.savings_goals import get_savings_goals

        return get_savings_goals(self.user_id, status=str(arguments.get("status") or "active"))

    def _create_savings_goal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.savings_goals import create_savings_goal

        return create_savings_goal(self.user_id, {**arguments, "context": self._savings_context()})

    def _update_savings_goal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.savings_goals import update_savings_goal

        goal_id = str(arguments.get("goal_id") or "")
        payload = {key: value for key, value in arguments.items() if key != "goal_id"}
        return update_savings_goal(self.user_id, goal_id, payload)

    def _archive_savings_goal(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.savings_goals import archive_savings_goal

        return archive_savings_goal(self.user_id, str(arguments.get("goal_id") or ""))

    def _budget_context(self, scope: str = "cycle") -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        from spectra.savings_goals import get_savings_goals
        from spectra.web import server

        scope = scope if scope in {"cycle", "90d", "ytd"} else "cycle"
        summary = self._jsonable_response(server.api_summary(self.request, scope=scope))
        budget = self._jsonable_response(server.api_budget(self.request))
        goals = get_savings_goals(self.user_id, status="active")
        return summary, budget, goals

    def _get_budget_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.budget_planner import get_budget_status_for_chat

        scope = str(arguments.get("scope") or "cycle")
        summary, budget, _goals = self._budget_context(scope)
        return get_budget_status_for_chat(self.user_id, scope=scope, summary_payload=summary, budget_payload=budget)

    def _recommend_budget_plan(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.budget_planner import recommend_budget_plan

        scope = str(arguments.get("scope") or "cycle")
        summary, budget, goals = self._budget_context(scope)
        return recommend_budget_plan(
            self.user_id,
            scope=scope,
            goal_id=str(arguments.get("goal_id") or "") or None,
            target_savings_amount=arguments.get("target_savings_amount"),
            summary_payload=summary,
            budget_payload=budget,
            goals_payload=goals,
        )

    def _simulate_budget_adjustment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.budget_planner import simulate_budget_adjustment

        scope = str(arguments.get("scope") or "cycle")
        summary, budget, goals = self._budget_context(scope)
        return simulate_budget_adjustment(
            self.user_id,
            adjustments=list(arguments.get("adjustments") or []),
            scope=scope,
            goal_id=str(arguments.get("goal_id") or "") or None,
            summary_payload=summary,
            budget_payload=budget,
            goals_payload=goals,
        )

    def _compare_budget_vs_actual(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.budget_planner import compare_budget_vs_actual

        scope = str(arguments.get("scope") or "cycle")
        summary, budget, _goals = self._budget_context(scope)
        return compare_budget_vs_actual(self.user_id, scope=scope, summary_payload=summary, budget_payload=budget)

    def _update_budget_limit(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.budget_planner import update_budget_limit

        return update_budget_limit(
            self.user_id,
            category=str(arguments.get("category") or ""),
            limit=arguments.get("limit"),
        )

    def _upsert_budget_plan(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.budget_planner import upsert_budget_plan

        return upsert_budget_plan(self.user_id, budgets=list(arguments.get("budgets") or []))

    def _get_conversation_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.context import build_chat_context

        session_id = str(arguments.get("session_id") or "").strip()
        if not session_id:
            raise ValueError("session_id is required")
        return build_chat_context(self.user_id, session_id, current_message="")

    def _get_user_memories(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.memory import get_user_memories

        memory_types = list(arguments.get("memory_types") or [])
        return {"memories": get_user_memories(self.user_id, memory_types=memory_types, limit=50)}

    def _remember_user_preference(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.memory import upsert_user_memory

        memory = upsert_user_memory(
            user_id=self.user_id,
            memory_type=str(arguments.get("memory_type") or "preference"),
            key=str(arguments.get("key") or ""),
            value=dict(arguments.get("value") or {}),
            source="chat_confirmed",
            confidence=1.0,
        )
        return {"ok": True, "memory": memory, "reason": str(arguments.get("reason") or "")}

    def _forget_user_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.memory import delete_user_memory

        memory = delete_user_memory(self.user_id, str(arguments.get("memory_id") or ""))
        return {"ok": True, "memory": memory}

    def _validate_category(self, category: str) -> None:
        from spectra.web import server

        with server._get_db() as db:
            rows = db._conn.execute(
                "SELECT DISTINCT category FROM app_tx_history WHERE user_id = ? AND category != ?",
                (self.user_id, UNCATEGORIZED),
            ).fetchall()
        known = {normalize_category(row[0]) for row in rows}
        known.update(normalize_category(row[1]) for row in build_seed_data())
        if category not in known:
            raise ValueError("Unknown category")

    @staticmethod
    def _positive_int(value: Any, *, default: int, max_value: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return min(max(parsed, 1), max_value)

    @staticmethod
    def _jsonable_response(value: Any) -> dict[str, Any]:
        if isinstance(value, JSONResponse):
            return {"error": "Tool returned an error response", "status_code": value.status_code}
        if isinstance(value, dict):
            return value
        return {"result": value}
