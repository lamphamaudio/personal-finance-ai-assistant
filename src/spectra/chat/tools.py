"""Allowlisted chatbot tool registry."""

from __future__ import annotations

from spectra.chat.models import RegisteredTool


def _object_schema(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_TOOLS: dict[str, RegisteredTool] = {
    "get_current_user": RegisteredTool(
        name="get_current_user",
        description="Return the authenticated Spectra user context with sensitive account fields masked.",
        parameters=_object_schema({}),
        required_scope="account.read_basic",
    ),
    "get_account_summary": RegisteredTool(
        name="get_account_summary",
        description="Return aggregate spending summary for the current cycle, last 90 days, or year to date.",
        parameters=_object_schema(
            {
                "scope": {
                    "type": "string",
                    "enum": ["cycle", "90d", "ytd"],
                    "description": "Summary window. Defaults to cycle.",
                }
            }
        ),
        required_scope="analytics.read",
    ),
    "get_transactions": RegisteredTool(
        name="get_transactions",
        description="Return a bounded filtered list of transaction rows when details are necessary.",
        parameters=_object_schema(
            {
                "page": {"type": "integer", "minimum": 1, "default": 1},
                "per_page": {"type": "integer", "minimum": 1, "maximum": 50, "default": 20},
                "category": {"type": "string", "default": ""},
                "uncategorized_only": {"type": "boolean", "default": False},
                "search": {"type": "string", "default": ""},
                "date_from": {"type": "string", "default": ""},
                "date_to": {"type": "string", "default": ""},
            }
        ),
        required_scope="transactions.read_detail",
    ),
    "get_category_options": RegisteredTool(
        name="get_category_options",
        description="Return known transaction category options for the authenticated user.",
        parameters=_object_schema({}),
        required_scope="categories.read",
    ),
    "update_transaction_category": RegisteredTool(
        name="update_transaction_category",
        description="Update one transaction category after explicit user confirmation.",
        parameters=_object_schema(
            {
                "tx_id": {"type": "string"},
                "category": {"type": "string"},
                "apply_to_future": {"type": "boolean", "default": False},
            },
            required=["tx_id", "category"],
        ),
        required_scope="category.update",
        read_only=False,
    ),
    "test_category_rule": RegisteredTool(
        name="test_category_rule",
        description="Preview whether a category memory rule would match existing transactions.",
        parameters=_object_schema(
            {
                "rule_type": {"type": "string", "enum": ["contains", "regex"], "default": "contains"},
                "pattern": {"type": "string"},
                "sample_text": {"type": "string", "default": ""},
            },
            required=["pattern"],
        ),
        required_scope="rules.read",
    ),
    "create_category_rule": RegisteredTool(
        name="create_category_rule",
        description="Create a category memory rule after explicit user confirmation.",
        parameters=_object_schema(
            {
                "rule_type": {"type": "string", "enum": ["contains", "regex"], "default": "contains"},
                "pattern": {"type": "string"},
                "category": {"type": "string"},
            },
            required=["pattern", "category"],
        ),
        required_scope="rules.write",
        read_only=False,
    ),
    "get_category_rules": RegisteredTool(
        name="get_category_rules",
        description="Return active category rules.",
        parameters=_object_schema({}),
        required_scope="rules.read",
    ),
    "get_learning_summary": RegisteredTool(
        name="get_learning_summary",
        description="Return recent category learning summary.",
        parameters=_object_schema({}),
        required_scope="memory.read",
    ),
    "get_anomalies": RegisteredTool(
        name="get_anomalies",
        description="Return unusual or suspicious financial activity for the authenticated user.",
        parameters=_object_schema(
            {
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                "scope": {"type": "string", "enum": ["cycle", "30d", "90d"], "default": "cycle"},
            }
        ),
        required_scope="anomaly.read",
    ),
    "get_balance_forecast": RegisteredTool(
        name="get_balance_forecast",
        description="Return estimated end-of-month balance forecast and spending trend.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["current_month"], "default": "current_month"},
            }
        ),
        required_scope="forecast.read",
    ),
    "explain_anomaly": RegisteredTool(
        name="explain_anomaly",
        description="Explain why a specific anomaly is unusual for the authenticated user.",
        parameters=_object_schema({"anomaly_id": {"type": "string"}}, required=["anomaly_id"]),
        required_scope="anomaly.read",
    ),
    "get_financial_health_score": RegisteredTool(
        name="get_financial_health_score",
        description="Return the authenticated user's deterministic budgeting and cashflow health score.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
                "month": {"type": "string", "default": ""},
                "refresh": {"type": "boolean", "default": False},
            }
        ),
        required_scope="financial_health.read",
    ),
    "plan_savings_goal": RegisteredTool(
        name="plan_savings_goal",
        description="Calculate whether the authenticated user can reach a saving goal by a target date.",
        parameters=_object_schema(
            {
                "name": {"type": "string"},
                "target_amount": {"type": "number"},
                "current_amount": {"type": "number", "default": 0},
                "target_date": {"type": "string"},
                "currency": {"type": "string", "default": "VND"},
            },
            required=["name", "target_amount", "target_date"],
        ),
        required_scope="goals.read",
    ),
    "simulate_savings_adjustment": RegisteredTool(
        name="simulate_savings_adjustment",
        description="Simulate whether reducing spending in categories helps reach a saving goal.",
        parameters=_object_schema(
            {
                "target_amount": {"type": "number"},
                "current_amount": {"type": "number", "default": 0},
                "target_date": {"type": "string"},
                "adjustments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "monthly_reduction": {"type": "number"},
                        },
                        "required": ["category", "monthly_reduction"],
                        "additionalProperties": False,
                    },
                },
                "currency": {"type": "string", "default": "VND"},
            },
            required=["target_amount", "target_date", "adjustments"],
        ),
        required_scope="goals.read",
    ),
    "get_savings_goals": RegisteredTool(
        name="get_savings_goals",
        description="Return the authenticated user's saving goals and progress.",
        parameters=_object_schema(
            {"status": {"type": "string", "enum": ["active", "completed", "paused", "archived", "all"], "default": "active"}}
        ),
        required_scope="goals.read",
    ),
    "create_savings_goal": RegisteredTool(
        name="create_savings_goal",
        description="Create a saving goal after explicit user confirmation.",
        parameters=_object_schema(
            {
                "name": {"type": "string"},
                "target_amount": {"type": "number"},
                "current_amount": {"type": "number", "default": 0},
                "target_date": {"type": "string"},
                "currency": {"type": "string", "default": "VND"},
            },
            required=["name", "target_amount", "target_date"],
        ),
        required_scope="goals.write",
        read_only=False,
    ),
    "update_savings_goal": RegisteredTool(
        name="update_savings_goal",
        description="Update a saving goal after explicit user confirmation.",
        parameters=_object_schema(
            {
                "goal_id": {"type": "string"},
                "name": {"type": "string"},
                "target_amount": {"type": "number"},
                "current_amount": {"type": "number"},
                "target_date": {"type": "string"},
                "status": {"type": "string", "enum": ["active", "completed", "paused", "archived"]},
            },
            required=["goal_id"],
        ),
        required_scope="goals.write",
        read_only=False,
    ),
    "archive_savings_goal": RegisteredTool(
        name="archive_savings_goal",
        description="Archive a saving goal after explicit user confirmation.",
        parameters=_object_schema({"goal_id": {"type": "string"}}, required=["goal_id"]),
        required_scope="goals.write",
        read_only=False,
    ),
    "get_budget_status": RegisteredTool(
        name="get_budget_status",
        description="Return budget status, actual spending, remaining budget, and projected over-budget risks.",
        parameters=_object_schema({"scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"}}),
        required_scope="budget.read",
    ),
    "recommend_budget_plan": RegisteredTool(
        name="recommend_budget_plan",
        description="Recommend a deterministic category-level budget plan.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
                "goal_id": {"type": "string", "default": ""},
                "target_savings_amount": {"type": "number"},
            }
        ),
        required_scope="budget.read",
    ),
    "simulate_budget_adjustment": RegisteredTool(
        name="simulate_budget_adjustment",
        description="Simulate the impact of changing one or more category budget limits.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
                "goal_id": {"type": "string", "default": ""},
                "adjustments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"category": {"type": "string"}, "limit": {"type": "number"}},
                        "required": ["category", "limit"],
                        "additionalProperties": False,
                    },
                },
            },
            required=["adjustments"],
        ),
        required_scope="budget.read",
    ),
    "compare_budget_vs_actual": RegisteredTool(
        name="compare_budget_vs_actual",
        description="Compare actual spending against current budget limits.",
        parameters=_object_schema({"scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"}}),
        required_scope="budget.read",
    ),
    "update_budget_limit": RegisteredTool(
        name="update_budget_limit",
        description="Update one category budget limit after explicit user confirmation.",
        parameters=_object_schema({"category": {"type": "string"}, "limit": {"type": "number"}}, required=["category", "limit"]),
        required_scope="budget.write",
        read_only=False,
    ),
    "upsert_budget_plan": RegisteredTool(
        name="upsert_budget_plan",
        description="Create or update multiple budget limits after explicit user confirmation.",
        parameters=_object_schema(
            {
                "budgets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"category": {"type": "string"}, "limit": {"type": "number"}},
                        "required": ["category", "limit"],
                        "additionalProperties": False,
                    },
                }
            },
            required=["budgets"],
        ),
        required_scope="budget.write",
        read_only=False,
    ),
    "get_conversation_context": RegisteredTool(
        name="get_conversation_context",
        description="Return compact recent conversation context for the authenticated user's current chat session.",
        parameters=_object_schema({"session_id": {"type": "string"}}, required=["session_id"]),
        required_scope="memory.read",
    ),
    "get_user_memories": RegisteredTool(
        name="get_user_memories",
        description="Return safe user memories and preferences for the authenticated user.",
        parameters=_object_schema(
            {
                "memory_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "preference",
                            "conversation_summary",
                            "last_goal_plan",
                            "last_budget_plan",
                            "last_transaction_candidates",
                            "category_preference",
                            "safety_preference",
                            "ui_preference",
                        ],
                    },
                }
            }
        ),
        required_scope="memory.read",
    ),
    "remember_user_preference": RegisteredTool(
        name="remember_user_preference",
        description="Remember a stable user preference after explicit user confirmation.",
        parameters=_object_schema(
            {
                "memory_type": {
                    "type": "string",
                    "enum": ["preference", "safety_preference", "ui_preference"],
                    "default": "preference",
                },
                "key": {"type": "string"},
                "value": {"type": "object"},
                "reason": {"type": "string"},
            },
            required=["key", "value", "reason"],
        ),
        required_scope="memory.write",
        read_only=False,
    ),
    "forget_user_memory": RegisteredTool(
        name="forget_user_memory",
        description="Delete a user memory after explicit user confirmation.",
        parameters=_object_schema({"memory_id": {"type": "string"}}, required=["memory_id"]),
        required_scope="memory.write",
        read_only=False,
    ),
}


def get_registered_tools() -> dict[str, RegisteredTool]:
    return dict(_TOOLS)


def get_tool(name: str) -> RegisteredTool | None:
    return _TOOLS.get(name)


def openai_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in _TOOLS.values()
    ]
