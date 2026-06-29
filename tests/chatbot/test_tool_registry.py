from spectra.chat.tools import get_registered_tools


def test_tool_registry_contains_phase_3_tools_without_destructive_tools():
    tools = get_registered_tools()

    assert {
        "get_current_user",
        "get_account_summary",
        "get_transactions",
        "get_category_options",
        "update_transaction_category",
        "test_category_rule",
        "create_category_rule",
        "get_category_rules",
        "get_learning_summary",
        "get_anomalies",
        "get_balance_forecast",
        "explain_anomaly",
        "get_financial_health_score",
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
        "simulate_income_change",
        "get_spending_patterns",
        "get_peer_benchmark",
        "get_conversation_context",
        "get_user_memories",
        "remember_user_preference",
        "forget_user_memory",
    } == set(tools)
    assert tools["update_transaction_category"].read_only is False
    assert tools["create_category_rule"].read_only is False
    assert tools["test_category_rule"].read_only is True
    assert tools["get_anomalies"].read_only is True
    assert tools["get_balance_forecast"].read_only is True
    assert tools["explain_anomaly"].read_only is True
    assert tools["get_financial_health_score"].read_only is True
    assert tools["plan_savings_goal"].read_only is True
    assert tools["simulate_savings_adjustment"].read_only is True
    assert tools["get_savings_goals"].read_only is True
    assert tools["create_savings_goal"].read_only is False
    assert tools["update_savings_goal"].read_only is False
    assert tools["archive_savings_goal"].read_only is False
    assert tools["get_budget_status"].read_only is True
    assert tools["recommend_budget_plan"].read_only is True
    assert tools["simulate_budget_adjustment"].read_only is True
    assert tools["compare_budget_vs_actual"].read_only is True
    assert tools["update_budget_limit"].read_only is False
    assert tools["upsert_budget_plan"].read_only is False
    assert tools["get_recurring_transactions"].read_only is True
    assert tools["compare_period_spending"].read_only is True
    assert tools["explain_budget_overrun"].read_only is True
    assert tools["get_cashflow_calendar"].read_only is True
    assert tools["simulate_purchase_impact"].read_only is True
    assert tools["get_debt_summary"].read_only is True
    assert tools["get_emergency_fund_status"].read_only is True
    assert tools["simulate_income_change"].read_only is True
    assert tools["get_spending_patterns"].read_only is True
    assert tools["get_peer_benchmark"].read_only is True
    assert not any(tool.dangerous for tool in tools.values())
    assert "reset_db" not in tools
    assert "learning_reapply" not in tools
    assert "users" not in tools
    assert "stats" not in tools
