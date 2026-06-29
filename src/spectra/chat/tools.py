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
        description="Return aggregate spending, income, category, and merchant summary for a scope or explicit date range.",
        parameters=_object_schema(
            {
                "scope": {
                    "type": "string",
                    "enum": ["cycle", "90d", "ytd"],
                    "description": "Summary window. Defaults to cycle when date_from/date_to are not provided.",
                },
                "date_from": {
                    "type": "string",
                    "default": "",
                    "description": "Optional inclusive ISO date, for example 2026-05-01. Use with date_to.",
                },
                "date_to": {
                    "type": "string",
                    "default": "",
                    "description": "Optional exclusive ISO date, for example 2026-06-01 for May 2026. Use with date_from.",
                },
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
                "target_savings_amount": {
                    "type": "number",
                    "description": "How much the user wants to SAVE (e.g. 'tiết kiệm/để dành X'). Not the salary.",
                },
                "monthly_income": {
                    "type": "number",
                    "description": "User-stated monthly income/salary (e.g. 'lương 8tr' -> 8000000). Overrides income from transaction data.",
                },
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
    "get_recurring_transactions": RegisteredTool(
        name="get_recurring_transactions",
        description="Return estimated recurring payments, subscriptions, recurring income, and price changes.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            }
        ),
        required_scope="analytics.read",
    ),
    "compare_period_spending": RegisteredTool(
        name="compare_period_spending",
        description="Compare spending, income, categories, and merchants between two explicit periods or current versus previous month.",
        parameters=_object_schema(
            {
                "period_a_from": {"type": "string", "default": ""},
                "period_a_to": {"type": "string", "default": ""},
                "period_b_from": {"type": "string", "default": ""},
                "period_b_to": {"type": "string", "default": ""},
            }
        ),
        required_scope="analytics.read",
    ),
    "explain_budget_overrun": RegisteredTool(
        name="explain_budget_overrun",
        description="Explain which categories and transactions are driving current over-budget or at-risk budget status.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
                "category": {"type": "string", "default": ""},
            }
        ),
        required_scope="budget.read",
    ),
    "get_cashflow_calendar": RegisteredTool(
        name="get_cashflow_calendar",
        description="Return an estimated daily cashflow calendar from current balance, daily spend, and recurring events.",
        parameters=_object_schema({"days": {"type": "integer", "minimum": 7, "maximum": 45, "default": 30}}),
        required_scope="forecast.read",
    ),
    "simulate_purchase_impact": RegisteredTool(
        name="simulate_purchase_impact",
        description="Simulate whether a planned purchase affects current budget, forecast balance, or savings goals.",
        parameters=_object_schema(
            {
                "amount": {"type": "number"},
                "category": {"type": "string", "default": ""},
                "purchase_date": {"type": "string", "default": ""},
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
            },
            required=["amount"],
        ),
        required_scope="forecast.read",
    ),
    "get_debt_summary": RegisteredTool(
        name="get_debt_summary",
        description="Infer debt-like payments from transaction history without claiming outstanding debt balance.",
        parameters=_object_schema({"scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"}}),
        required_scope="analytics.read",
    ),
    "get_emergency_fund_status": RegisteredTool(
        name="get_emergency_fund_status",
        description="Estimate emergency fund coverage from current balance and essential historical expenses.",
        parameters=_object_schema({"months_target": {"type": "number", "default": 3}}),
        required_scope="forecast.read",
    ),
    "simulate_income_change": RegisteredTool(
        name="simulate_income_change",
        description="Simulate how a monthly income increase or decrease changes cashflow surplus, savings rate, and goal feasibility.",
        parameters=_object_schema(
            {
                "income_delta": {
                    "type": "number",
                    "description": "Monthly income change in VND. Positive = increase, negative = decrease. E.g. +3000000 for +3tr/month.",
                },
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "cycle"},
            },
            required=["income_delta"],
        ),
        required_scope="forecast.read",
    ),
    "get_peer_benchmark": RegisteredTool(
        name="get_peer_benchmark",
        description=(
            "Compare the user's spending allocation (needs/wants/savings) against general reference benchmarks "
            "(50/30/20 rule and income-bracket norms). Use for peer/social comparison questions like "
            "'so sánh với người cùng tuổi/cùng địa vị', 'chi tiêu của tôi đã hợp lý chưa', "
            "'người có lương X thường chi bao nhiêu'. Does NOT use other users' real data."
        ),
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "90d"},
                "monthly_income_override": {
                    "type": "number",
                    "description": "Optional monthly income in VND to use instead of inferring from transactions.",
                },
            }
        ),
        required_scope="analytics.read",
    ),
    "get_spending_patterns": RegisteredTool(
        name="get_spending_patterns",
        description="Analyze historical spending patterns by weekday, day of month, or week of month to reveal when the user spends most.",
        parameters=_object_schema(
            {
                "scope": {"type": "string", "enum": ["cycle", "90d", "ytd"], "default": "90d"},
                "group_by": {
                    "type": "string",
                    "enum": ["weekday", "day_of_month", "week_of_month"],
                    "default": "weekday",
                    "description": "How to group transactions: by day of week, by day of month, or by week of month.",
                },
            }
        ),
        required_scope="analytics.read",
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
