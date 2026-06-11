"""Tool execution guardrails for verifying parameter safety and write permissions."""

from __future__ import annotations

from typing import Any
from spectra.chat.tools import get_tool
from spectra.chat.confirmation import pending_actions


class ToolGuardResult:
    def __init__(self, passed: bool, reason: str | None = None, status: str = "rejected"):
        self.passed = passed
        self.reason = reason
        self.status = status


class UnregisteredToolGuard:
    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: str | None,
    ) -> ToolGuardResult:
        tool = get_tool(tool_name)
        if not tool:
            return ToolGuardResult(False, "Tool is not registered for the chatbot.", status="rejected")
        if tool.dangerous:
            return ToolGuardResult(
                False, "Admin and destructive tools are not available to the chatbot.", status="rejected"
            )
        if tool.requires_session and not user_id:
            return ToolGuardResult(False, "Authenticated session is required.", status="rejected")
        return ToolGuardResult(True)


class ToolParameterGuard:
    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        user_id: str | None,
    ) -> ToolGuardResult:
        # Check no user_id parameter injection for tools that strictly forbid it
        NO_USER_ID_TOOLS = {
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
            "get_recurring_transactions",
            "compare_period_spending",
            "explain_budget_overrun",
            "get_cashflow_calendar",
            "simulate_purchase_impact",
            "get_debt_summary",
            "get_emergency_fund_status",
            "get_conversation_context",
            "get_user_memories",
            "remember_user_preference",
            "forget_user_memory",
            "get_financial_health_score",
        }
        if "user_id" in arguments and tool_name in NO_USER_ID_TOOLS:
            return ToolGuardResult(
                False, f"user_id is not accepted for this tool.", status="rejected"
            )

        # Check financial health score arguments
        if tool_name == "get_financial_health_score":
            if bool(arguments.get("refresh") or False):
                return ToolGuardResult(
                    False, "refresh is not available to chatbot tools.", status="rejected"
                )

        # Check memory arguments
        if tool_name in {"remember_user_preference", "forget_user_memory"}:
            from spectra.chat.memory import LONG_TERM_MEMORY_TYPES, has_sensitive_memory_payload

            if has_sensitive_memory_payload(arguments):
                return ToolGuardResult(False, "Memory payload contains sensitive data.", status="rejected")
            if tool_name == "remember_user_preference":
                memory_type = str(arguments.get("memory_type") or "preference")
                if memory_type not in LONG_TERM_MEMORY_TYPES:
                    return ToolGuardResult(
                        False, "Only stable long-term preference memory types are supported.", status="rejected"
                    )

        return ToolGuardResult(True)


class WriteConfirmationGuard:
    def check(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        confirmation_id: str | None,
        user_id: str | None,
    ) -> ToolGuardResult:
        tool = get_tool(tool_name)
        if not tool or tool.read_only:
            return ToolGuardResult(True)

        if not confirmation_id:
            return ToolGuardResult(
                False, "Write tool requires a valid pending confirmation.", status="rejected"
            )

        action = pending_actions.get(confirmation_id)
        if not action:
            return ToolGuardResult(False, "Unknown confirmation_id.", status="rejected")
        if action.user_id != user_id:
            return ToolGuardResult(
                False, "Confirmation does not belong to this user.", status="rejected"
            )
        if action.status != "pending":
            return ToolGuardResult(
                False, f"Confirmation is {action.status}.", status="rejected"
            )
        if action.tool_name != tool_name or action.tool_arguments != arguments:
            return ToolGuardResult(
                False, "Confirmation does not match this tool call.", status="rejected"
            )

        return ToolGuardResult(True)
