"""Permission-aware allowlisted tool executor for the chatbot."""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
import httpx
from jsonschema import validate, ValidationError
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, retry_if_exception

from spectra.chat.audit import log_write_tool_call
from spectra.chat.confirmation import pending_actions
from spectra.chat.models import ToolExecutionResult
from spectra.chat.redaction import mask_account_number, redact_payload
from spectra.chat.tools import get_tool
from spectra.categories import UNCATEGORIZED, normalize_category
from spectra.ml_classifier import build_seed_data
from spectra.chat.tracing import trace_span
from spectra.config import load_settings

logger = logging.getLogger("spectra.chat.executor")

# Try importing psycopg operational error if available
try:
    from psycopg import OperationalError as PsycopgOperationalError
    _PSYGOPG_ERRORS = (PsycopgOperationalError,)
except ImportError:
    _PSYGOPG_ERRORS = ()

TRANSIENT_EXCEPTIONS = (
    sqlite3.OperationalError,
    TimeoutError,
    asyncio.TimeoutError,
    httpx.RequestError,
    httpx.HTTPStatusError,
) + _PSYGOPG_ERRORS


def is_transient_exception(exc: Exception) -> bool:
    """Check if the exception is due to transient system or network conditions."""
    if isinstance(exc, TRANSIENT_EXCEPTIONS):
        return True
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        if exc.response.status_code >= 500:
            return True
    return False


class ToolCache:
    """Thread-safe, session-scoped in-memory cache for read-only chatbot tools."""
    def __init__(self) -> None:
        # Key: (user_id, session_id, tool_name, arguments_json) -> (data, expiry)
        self._cache: Dict[tuple[str, str, str, str], tuple[Any, float]] = {}

    def get(self, user_id: str, session_id: str | None, tool_name: str, arguments: dict[str, Any]) -> Any | None:
        sess = str(session_id or "").strip()
        args_json = json.dumps(arguments, sort_keys=True)
        key = (user_id, sess, tool_name, args_json)
        if key in self._cache:
            data, expiry = self._cache[key]
            if time.time() < expiry:
                return data
            else:
                del self._cache[key]
        return None

    def set(self, user_id: str, session_id: str | None, tool_name: str, arguments: dict[str, Any], data: Any, ttl: float) -> None:
        sess = str(session_id or "").strip()
        args_json = json.dumps(arguments, sort_keys=True)
        key = (user_id, sess, tool_name, args_json)
        self._cache[key] = (data, time.time() + ttl)

    def invalidate_session(self, user_id: str, session_id: str | None) -> None:
        """Clear the cache for a specific session after write actions."""
        sess = str(session_id or "").strip()
        keys_to_del = [k for k in self._cache if k[0] == user_id and k[1] == sess]
        for k in keys_to_del:
            try:
                del self._cache[k]
            except KeyError:
                pass


# Global thread-safe tool cache instance
_TOOL_CACHE = ToolCache()



def sanitize_arguments(arguments: dict[str, Any], parameters_schema: dict[str, Any]) -> dict[str, Any]:
    """Helper to clean user_id and clamp out-of-bound arguments before schema validation."""
    args = dict(arguments)
    properties = parameters_schema.get("properties", {})
    
    # 1. Remove user_id if not explicitly expected by schema properties
    if "user_id" in args and "user_id" not in properties:
        args.pop("user_id")
        
    # 2. Clamp numeric fields to their schema minimum/maximum limits
    for prop_name, prop_schema in properties.items():
        if prop_name in args:
            val = args[prop_name]
            prop_type = prop_schema.get("type")
            if prop_type in ("integer", "number"):
                try:
                    if prop_type == "integer":
                        numeric_val = int(val)
                    else:
                        numeric_val = float(val)
                        
                    if "minimum" in prop_schema and numeric_val < prop_schema["minimum"]:
                        numeric_val = prop_schema["minimum"]
                    if "maximum" in prop_schema and numeric_val > prop_schema["maximum"]:
                        numeric_val = prop_schema["maximum"]
                        
                    args[prop_name] = numeric_val
                except (ValueError, TypeError):
                    pass
    return args


class ToolExecutor:
    def __init__(self, request: Request, user_id: str):
        self.request = request
        self.user_id = str(user_id or "").strip()
        if self.user_id:
            try:
                self.request.state.spectra_user_id = self.user_id
            except Exception:
                pass

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        confirmation_id: str | None = None,
        session_id: str | None = None,
    ) -> ToolExecutionResult:
        arguments = arguments or {}
        from spectra.chat.guardrails.engine import guardrail_engine
        guard_result = guardrail_engine.check_tool_call(tool_name, arguments, confirmation_id, self.user_id)
        if guard_result:
            return guard_result
        tool = get_tool(tool_name)
        if not tool:
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error="Tool is not registered for the chatbot.",
            )

        # Sanitize arguments (remove user_id and clamp values)
        arguments = sanitize_arguments(arguments, tool.parameters)

        # 1. Input Schema Validation
        try:
            validate(instance=arguments, schema=tool.parameters)
        except ValidationError as e:
            logger.warning("Input validation failed for tool %s: %s", tool_name, e.message)
            return ToolExecutionResult(
                tool_name=tool_name,
                status="rejected",
                error=f"Input validation failed: {e.message}",
            )

        # 2. Cache Check (Read-only tools only)
        settings = load_settings()
        if tool.read_only:
            cached_data = _TOOL_CACHE.get(self.user_id, session_id, tool_name, arguments)
            if cached_data is not None:
                logger.info("Cache hit for read-only tool %s", tool_name)
                return ToolExecutionResult(tool_name=tool_name, status="success", data=cached_data)

        # Helper runner logic for tool execution
        def run_sync_logic() -> Any:
            if tool_name == "get_current_user":
                return self._get_current_user()
            elif tool_name == "get_account_summary":
                return self._get_account_summary(arguments)
            elif tool_name == "get_transactions":
                return self._get_transactions(arguments)
            elif tool_name == "get_category_options":
                return self._get_category_options()
            elif tool_name == "update_transaction_category":
                return self._update_transaction_category(arguments)
            elif tool_name == "test_category_rule":
                return self._test_category_rule(arguments)
            elif tool_name == "create_category_rule":
                return self._create_category_rule(arguments)
            elif tool_name == "get_category_rules":
                return self._get_category_rules()
            elif tool_name == "get_learning_summary":
                return self._get_learning_summary()
            elif tool_name == "get_anomalies":
                return self._get_anomalies(arguments)
            elif tool_name == "get_balance_forecast":
                return self._get_balance_forecast(arguments)
            elif tool_name == "explain_anomaly":
                return self._explain_anomaly(arguments)
            elif tool_name == "get_financial_health_score":
                return self._get_financial_health_score(arguments)
            elif tool_name == "plan_savings_goal":
                return self._plan_savings_goal(arguments)
            elif tool_name == "simulate_savings_adjustment":
                return self._simulate_savings_adjustment(arguments)
            elif tool_name == "get_savings_goals":
                return self._get_savings_goals(arguments)
            elif tool_name == "create_savings_goal":
                return self._create_savings_goal(arguments)
            elif tool_name == "update_savings_goal":
                return self._update_savings_goal(arguments)
            elif tool_name == "archive_savings_goal":
                return self._archive_savings_goal(arguments)
            elif tool_name == "get_budget_status":
                return self._get_budget_status(arguments)
            elif tool_name == "recommend_budget_plan":
                return self._recommend_budget_plan(arguments)
            elif tool_name == "simulate_budget_adjustment":
                return self._simulate_budget_adjustment(arguments)
            elif tool_name == "compare_budget_vs_actual":
                return self._compare_budget_vs_actual(arguments)
            elif tool_name == "update_budget_limit":
                return self._update_budget_limit(arguments)
            elif tool_name == "upsert_budget_plan":
                return self._upsert_budget_plan(arguments)
            elif tool_name == "get_recurring_transactions":
                return self._get_recurring_transactions(arguments)
            elif tool_name == "compare_period_spending":
                return self._compare_period_spending(arguments)
            elif tool_name == "explain_budget_overrun":
                return self._explain_budget_overrun(arguments)
            elif tool_name == "get_cashflow_calendar":
                return self._get_cashflow_calendar(arguments)
            elif tool_name == "simulate_purchase_impact":
                return self._simulate_purchase_impact(arguments)
            elif tool_name == "get_debt_summary":
                return self._get_debt_summary(arguments)
            elif tool_name == "get_emergency_fund_status":
                return self._get_emergency_fund_status(arguments)
            elif tool_name == "get_conversation_context":
                return self._get_conversation_context(arguments)
            elif tool_name == "get_user_memories":
                return self._get_user_memories(arguments)
            elif tool_name == "remember_user_preference":
                return self._remember_user_preference(arguments)
            elif tool_name == "forget_user_memory":
                return self._forget_user_memory(arguments)
            else:
                raise ValueError("Tool is not executable by the chatbot.")

        # 3. Execution with Timeout, Retry & Tracing
        with trace_span(tool_name, "tool", arguments) as rec:
            try:
                # Custom timeout or global default from settings
                timeout = getattr(tool, "timeout", settings.chat_tool_timeout)
                
                retrier = AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
                    retry=retry_if_exception(is_transient_exception),
                    reraise=True,
                )

                async def _run_in_executor() -> Any:
                    return await asyncio.get_running_loop().run_in_executor(None, run_sync_logic)

                try:
                    async for attempt in retrier:
                        with attempt:
                            data = await asyncio.wait_for(_run_in_executor(), timeout=timeout)
                except asyncio.TimeoutError:
                    raise TimeoutError(f"Tool {tool_name} execution timed out after {timeout} seconds.")

                # Output validation if tool defines an output schema (optional metadata)
                output_schema = getattr(tool, "output_schema", None)
                if output_schema:
                    try:
                        validate(instance=data, schema=output_schema)
                    except ValidationError as e:
                        logger.error("Output validation failed for tool %s: %s", tool_name, e.message)
                        raise ValueError(f"Tool output validation failed: {e.message}")

                # Success hooks
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
                    # Clear session cache when data is modified
                    _TOOL_CACHE.invalidate_session(self.user_id, session_id)

                if tool.read_only:
                    # Cache successful read-only results
                    _TOOL_CACHE.set(self.user_id, session_id, tool_name, arguments, data, settings.chat_tool_cache_ttl)

                redacted_data = redact_payload(data)
                rec.outputs = redacted_data
                return ToolExecutionResult(tool_name=tool_name, status="success", data=redacted_data)

            except Exception as e:
                error_msg = str(e)
                rec.error = error_msg
                rec.status = "error"
                logger.error("Error executing tool %s: %s", tool_name, error_msg, exc_info=True)

                if not tool.read_only and confirmation_id:
                    log_write_tool_call(
                        user_id=self.user_id,
                        session_id=session_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        status="error",
                        confirmation_id=confirmation_id,
                        error_message=error_msg,
                    )
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status="error",
                    error=f"Tool execution failed: {error_msg}",
                )



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
        result = server.api_summary(
            self.request,
            scope=scope,
            date_from=str(arguments.get("date_from") or ""),
            date_to=str(arguments.get("date_to") or ""),
        )
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
                user_id=self.user_id,
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
            preview = server._simulate_rule_impact(
                db,
                rule_type=rule_type,
                pattern=pattern,
                sample_text=sample_text,
                user_id=self.user_id,
            )
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
            rule = db.add_category_rule(rule_type=rule_type, pattern=pattern, category=category, user_id=self.user_id)
        return {"ok": True, "rule": rule}

    def _get_category_rules(self) -> dict[str, Any]:
        from spectra.web import server

        with server._get_db() as db:
            rules = [rule for rule in db.get_category_rules(self.user_id) if rule.get("is_active", True)]
        return {"rules": rules[:50]}

    def _get_learning_summary(self) -> dict[str, Any]:
        from spectra.web import server

        result = server.api_learning_summary(self.request)
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

    def _get_recurring_transactions(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import get_recurring_transactions

        return get_recurring_transactions(
            self.user_id,
            scope=str(arguments.get("scope") or "cycle"),
            limit=self._positive_int(arguments.get("limit"), default=10, max_value=20),
        )

    def _compare_period_spending(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import compare_period_spending

        return compare_period_spending(
            self.user_id,
            period_a_from=str(arguments.get("period_a_from") or ""),
            period_a_to=str(arguments.get("period_a_to") or ""),
            period_b_from=str(arguments.get("period_b_from") or ""),
            period_b_to=str(arguments.get("period_b_to") or ""),
        )

    def _explain_budget_overrun(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import explain_budget_overrun
        from spectra.web import server

        scope = str(arguments.get("scope") or "cycle")
        summary = self._jsonable_response(server.api_summary(self.request, scope=scope))
        budget = self._jsonable_response(server.api_budget(self.request))
        return explain_budget_overrun(
            self.user_id,
            scope=scope,
            category=str(arguments.get("category") or ""),
            summary_payload=summary,
            budget_payload=budget,
        )

    def _get_cashflow_calendar(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import get_cashflow_calendar

        days = self._positive_int(arguments.get("days"), default=30, max_value=45)
        days = max(days, 7)
        return get_cashflow_calendar(self.user_id, days=days, forecast_payload=self._get_balance_forecast({}))

    def _simulate_purchase_impact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import simulate_purchase_impact
        from spectra.savings_goals import get_savings_goals
        from spectra.web import server

        scope = str(arguments.get("scope") or "cycle")
        summary = self._jsonable_response(server.api_summary(self.request, scope=scope))
        budget = self._jsonable_response(server.api_budget(self.request))
        forecast = self._get_balance_forecast({})
        goals = get_savings_goals(self.user_id, status="active")
        return simulate_purchase_impact(
            self.user_id,
            amount=arguments.get("amount"),
            category=str(arguments.get("category") or ""),
            purchase_date=str(arguments.get("purchase_date") or ""),
            scope=scope,
            summary_payload=summary,
            budget_payload=budget,
            forecast_payload=forecast,
            goals_payload=goals,
        )

    def _get_debt_summary(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import get_debt_summary

        return get_debt_summary(self.user_id, scope=str(arguments.get("scope") or "cycle"))

    def _get_emergency_fund_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from spectra.chat.insight_tools import get_emergency_fund_status

        return get_emergency_fund_status(
            self.user_id,
            months_target=arguments.get("months_target") or 3,
            forecast_payload=self._get_balance_forecast({}),
        )

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
