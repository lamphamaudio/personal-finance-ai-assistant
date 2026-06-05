from datetime import date, timedelta

from spectra.chat.insight_tools import (
    compare_period_spending,
    explain_budget_overrun,
    get_debt_summary,
    get_emergency_fund_status,
    get_recurring_transactions,
    simulate_purchase_impact,
)


class _Conn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args, **_kwargs):
        return self

    def fetchall(self):
        return self.rows


class _Db:
    def __init__(self, rows):
        self._conn = _Conn(rows)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


def _patch_rows(monkeypatch, rows):
    from spectra.web import server

    monkeypatch.setattr(server, "_get_db", lambda: _Db(rows))


def test_recurring_detection_returns_monthly_summary(monkeypatch):
    today = date.today()
    rows = [
        ((today - timedelta(days=62)).isoformat(), "Netflix", -250_000, "Subscriptions", "Netflix monthly"),
        ((today - timedelta(days=31)).isoformat(), "Netflix", -250_000, "Subscriptions", "Netflix monthly"),
        (today.isoformat(), "Netflix", -250_000, "Subscriptions", "Netflix monthly"),
    ]
    _patch_rows(monkeypatch, rows)

    result = get_recurring_transactions("user-1", limit=50)

    assert result["summary"]["active_count"] == 1
    assert result["items"][0]["merchant"] == "Netflix"
    assert result["items"][0]["monthly_estimate"] > 0


def test_compare_period_spending_defaults_current_vs_previous(monkeypatch):
    today = date.today()
    current = today.replace(day=2)
    previous_start = date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    previous = previous_start.replace(day=2)
    rows = [
        (current.isoformat(), "Grab", -300_000, "Transport", ""),
        (previous.isoformat(), "Grab", -100_000, "Transport", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = compare_period_spending("user-1")

    assert result["totals"]["spent_delta"] == 200_000
    assert result["category_deltas"][0]["category"] == "Transport"


def test_budget_overrun_explanation_returns_top_drivers(monkeypatch):
    today = date.today()
    rows = [
        (today.isoformat(), "Restaurant A", -900_000, "Food", ""),
        (today.isoformat(), "Cafe B", -200_000, "Food", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = explain_budget_overrun(
        "user-1",
        budget_payload={"items": [{"category": "Food", "spent": 1_100_000, "limit": 1_000_000, "status": "red"}]},
    )

    assert result["summary"]["over_or_at_risk_count"] == 1
    assert result["categories"][0]["top_drivers"][0]["merchant"] == "Restaurant A"


def test_purchase_simulation_labels_not_recommended_when_balance_goes_negative():
    result = simulate_purchase_impact(
        "user-1",
        amount=2_000_000,
        summary_payload={"total_spent": 1_000_000},
        forecast_payload={"predicted_end_of_month_balance": 1_000_000},
        budget_payload={"items": [{"category": "Shopping", "spent": 0, "limit": 5_000_000}]},
        category="Shopping",
    )

    assert result["recommendation"]["label"] == "not_recommended"


def test_debt_summary_states_outstanding_balance_unavailable(monkeypatch):
    today = date.today()
    rows = [(today.isoformat(), "Bank Loan", -1_500_000, "Tra no", "loan installment")]
    _patch_rows(monkeypatch, rows)

    result = get_debt_summary("user-1")

    assert result["outstanding_balance_available"] is False
    assert result["summary"]["debt_like_payment_count"] == 1


def test_emergency_fund_uses_essential_monthly_spend(monkeypatch):
    today = date.today()
    rows = [
        ((today - timedelta(days=20)).isoformat(), "Rent", -3_000_000, "nha o", ""),
        ((today - timedelta(days=10)).isoformat(), "Cafe", -300_000, "Food", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = get_emergency_fund_status("user-1", months_target=3, forecast_payload={"current_balance": 9_000_000})

    assert result["monthly_essential_spend"] > 0
    assert result["target_amount"] > 0
