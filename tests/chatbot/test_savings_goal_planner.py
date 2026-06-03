from datetime import date

import pytest

from spectra.savings_goals import extract_goal_from_message, plan_savings_goal, simulate_savings_adjustment


def _future_date(months: int = 6) -> str:
    today = date.today()
    month = today.month - 1 + months
    year = today.year + month // 12
    month = month % 12 + 1
    return date(year, month, min(today.day, 28)).isoformat()


def test_plan_savings_goal_calculates_required_monthly_saving():
    result = plan_savings_goal(
        "user-1",
        name="Tiet kiem 20 trieu",
        target_amount=20_000_000,
        current_amount=0,
        target_date=_future_date(6),
        context={"average_monthly_income": 15_000_000, "average_monthly_expense": 11_200_000},
    )

    assert result["required_plan"]["required_monthly_saving"] == pytest.approx(3_333_333.33, abs=2)
    assert result["feasibility"]["label"] in {"challenging", "risky"}


def test_goal_already_achieved_when_current_amount_reaches_target():
    result = plan_savings_goal(
        "user-1",
        name="Emergency fund",
        target_amount=10_000_000,
        current_amount=10_000_000,
        target_date=_future_date(3),
        context={"average_monthly_income": 10_000_000, "average_monthly_expense": 5_000_000},
    )

    assert result["feasibility"]["label"] == "achieved"


def test_past_target_date_is_rejected():
    with pytest.raises(ValueError):
        plan_savings_goal("user-1", name="Bad", target_amount=1_000_000, target_date="2020-01-01")


def test_missing_income_data_returns_low_confidence():
    result = plan_savings_goal("user-1", name="Goal", target_amount=1_000_000, target_date=_future_date(3))

    assert result["feasibility"]["label"] == "insufficient_data"
    assert result["feasibility"]["confidence"] == "low"


def test_unrealistic_and_realistic_labels():
    unrealistic = plan_savings_goal(
        "user-1",
        name="Big",
        target_amount=100_000_000,
        target_date=_future_date(6),
        context={"average_monthly_income": 10_000_000, "average_monthly_expense": 8_000_000},
    )
    realistic = plan_savings_goal(
        "user-1",
        name="Small",
        target_amount=3_000_000,
        target_date=_future_date(6),
        context={"average_monthly_income": 10_000_000, "average_monthly_expense": 8_000_000},
    )

    assert unrealistic["feasibility"]["label"] == "unrealistic"
    assert realistic["feasibility"]["label"] == "realistic"


def test_simulate_savings_adjustment_improves_monthly_gap():
    result = simulate_savings_adjustment(
        "user-1",
        target_amount=20_000_000,
        current_amount=0,
        target_date=_future_date(6),
        adjustments=[{"category": "An uong", "monthly_reduction": 500_000}],
        context={"average_monthly_income": 15_000_000, "average_monthly_expense": 12_000_000},
    )

    assert result["impact"]["monthly_gap_after"] > result["impact"]["monthly_gap_before"]


def test_extract_goal_from_vietnamese_message_with_accents():
    result = extract_goal_from_message("Tôi muốn tiết kiệm 20 triệu trong 6 tháng thì làm sao?")

    assert result
    assert result["target_amount"] == 20_000_000
    assert result["target_date"] == _future_date(6)
