import pytest

from spectra.budget_planner import (
    get_budget_status_for_chat,
    recommend_budget_plan,
    simulate_budget_adjustment,
    update_budget_limit,
)


def _summary():
    return {
        "total_income": 15_000_000,
        "total_spent": 8_500_000,
        "currency": "VND",
        "by_category": {
            "Ăn uống": 3_500_000,
            "Mua sắm": 2_000_000,
            "Sức khỏe": 1_500_000,
            "Giải trí": 1_500_000,
        },
        "selected_period": {"start": "2026-06-01", "end": "2026-07-01", "label": "June 2026"},
    }


def _budget():
    return {
        "current_cycle": {"start": "2026-06-01", "end": "2026-07-01", "label": "June 2026"},
        "items": [
            {"category": "Ăn uống", "spent": 3_500_000, "limit": 3_000_000},
            {"category": "Mua sắm", "spent": 2_000_000, "limit": 2_500_000},
            {"category": "Sức khỏe", "spent": 1_500_000, "limit": 1_700_000},
        ],
    }


def test_budget_status_returns_projected_categories():
    result = get_budget_status_for_chat("user-1", summary_payload=_summary(), budget_payload=_budget())

    assert result["currency"] == "VND"
    assert result["summary"]["total_budget"] == 7_200_000
    assert any(item["status"] == "over" for item in result["categories"])


def test_recommend_budget_plan_prioritizes_flexible_categories():
    result = recommend_budget_plan("user-1", summary_payload=_summary(), budget_payload=_budget())

    assert result["recommended_budgets"]
    first_categories = [item["category"] for item in result["recommended_budgets"][:2]]
    assert "Sức khỏe" not in first_categories


def test_fixed_categories_are_not_aggressively_reduced():
    result = recommend_budget_plan("user-1", summary_payload=_summary(), budget_payload=_budget())
    health = next(item for item in result["recommended_budgets"] if item["category"] == "Sức khỏe")

    assert health["recommended_budget"] >= 1_350_000


def test_simulate_budget_adjustment_does_not_persist_and_changes_total():
    result = simulate_budget_adjustment(
        "user-1",
        adjustments=[{"category": "Ăn uống", "limit": 2_500_000}],
        summary_payload=_summary(),
        budget_payload=_budget(),
    )

    assert result["impact"]["budget_delta"] == -500_000


def test_budget_limit_must_be_non_negative():
    with pytest.raises(ValueError):
        update_budget_limit("user-1", category="Ăn uống", limit=-1)


def test_unknown_empty_category_is_rejected():
    with pytest.raises(ValueError):
        update_budget_limit("user-1", category="", limit=1_000_000)
