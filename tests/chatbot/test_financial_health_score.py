from spectra.financial_health import (
    calculate_financial_health_score,
    score_anomaly_risk,
    score_forecast_risk,
    score_level,
    score_savings_rate,
)


def test_score_level_maps_ranges():
    assert score_level(35) == "Yeu"
    assert score_level(52) == "Can cai thien"
    assert score_level(68) == "Trung binh kha"
    assert score_level(81) == "Tot"
    assert score_level(93) == "Rat tot"


def test_savings_rate_component_scoring():
    component = score_savings_rate(10_000_000, 2_200_000)

    assert component["score"] == 20
    assert component["value"] == 0.22


def test_negative_cashflow_reduces_score():
    result = calculate_financial_health_score(
        "user-1",
        summary_payload={
            "total_income": 10_000_000,
            "total_spent": 12_000_000,
            "by_category": {"An uong": 7_000_000, "Di lai": 5_000_000},
        },
        forecast_payload={"available": True, "current_balance": 1_000_000, "predicted_end_of_month_balance": -500_000},
    )

    assert 0 <= result["score"] <= 100
    assert result["summary"]["net_cashflow"] < 0
    assert result["score"] < 60


def test_high_anomaly_count_reduces_component():
    component = score_anomaly_risk({"summary": {"total": 5, "high": 1}, "anomalies": []})

    assert component["score"] == 4


def test_negative_forecast_balance_reduces_component():
    component = score_forecast_risk(
        {"available": True, "current_balance": 2_000_000, "predicted_end_of_month_balance": -100_000}
    )

    assert component["score"] == 0


def test_missing_income_data_is_reported():
    result = calculate_financial_health_score("user-1")

    assert "income" in result["missing_data"]
    assert result["confidence"] in {"low", "medium"}
