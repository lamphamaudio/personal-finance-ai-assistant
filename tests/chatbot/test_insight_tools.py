from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from spectra.chat.insight_tools import (
    compare_period_spending,
    explain_budget_overrun,
    get_debt_summary,
    get_emergency_fund_status,
    get_peer_benchmark,
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


def test_peer_benchmark_good_saver_compares_against_bracket(monkeypatch):
    today = date.today()
    rows = [
        ((today - timedelta(days=15)).isoformat(), "Salary", 45_000_000, "Thu nhap", ""),
        ((today - timedelta(days=14)).isoformat(), "Rent", -9_000_000, "nha o", ""),
        ((today - timedelta(days=10)).isoformat(), "Shopping", -6_000_000, "Mua sam", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = get_peer_benchmark("user-1", scope="90d")

    # ~15tr/thang => nhom thu nhap trung binh thap (10-20 trieu)
    assert "10-20" in result["income_bracket"]
    assert result["actual_allocation"]["savings_pct"] > result["benchmark_allocation"]["savings_pct"]
    assert result["comparison"]["savings"]["status"] == "better"
    assert result["overall_assessment"] in {"good", "on_track"}
    # Luon kem disclaimer khong phai du lieu peer that
    assert any("nguoi dung khac" in lim for lim in result["limitations"])


def test_peer_benchmark_low_saver_flags_needs_improvement(monkeypatch):
    today = date.today()
    rows = [
        ((today - timedelta(days=15)).isoformat(), "Salary", 45_000_000, "Thu nhap", ""),
        ((today - timedelta(days=14)).isoformat(), "Rent", -24_000_000, "nha o", ""),
        ((today - timedelta(days=10)).isoformat(), "Dining", -21_000_000, "Food", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = get_peer_benchmark("user-1", scope="90d")

    assert result["comparison"]["savings"]["status"] == "worse"
    assert result["overall_assessment"] == "needs_improvement"
    assert result["suggestions"]


def test_peer_benchmark_income_override_selects_high_bracket(monkeypatch):
    today = date.today()
    rows = [
        ((today - timedelta(days=10)).isoformat(), "Rent", -10_000_000, "nha o", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = get_peer_benchmark("user-1", scope="90d", monthly_income_override=50_000_000)

    assert "tren 40" in result["income_bracket"]
    assert result["monthly_income"] == 50_000_000


def test_peer_benchmark_without_income_returns_insufficient_data(monkeypatch):
    today = date.today()
    rows = [
        ((today - timedelta(days=10)).isoformat(), "Rent", -3_000_000, "nha o", ""),
    ]
    _patch_rows(monkeypatch, rows)

    result = get_peer_benchmark("user-1", scope="90d")

    assert result["status"] == "insufficient_data"


def test_auto_sort_reverses_when_older_sent_as_a(monkeypatch):
    """Ensure that if period_a is older than period_b, they are swapped so period_a is always the newer one."""
    _patch_rows(monkeypatch, [])
    # May 2026 vs June 2026
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-05-01",
        period_a_to="2026-06-01",
        period_b_from="2026-06-01",
        period_b_to="2026-07-01",
    )
    assert result["period_a"]["start"] == "2026-06-01"
    assert result["period_a"]["label"] == "current"
    assert result["period_b"]["start"] == "2026-05-01"
    assert result["period_b"]["label"] == "previous"


def test_auto_sort_no_change_when_correct_order(monkeypatch):
    """Ensure that if period_a is already newer than period_b, no swap occurs."""
    _patch_rows(monkeypatch, [])
    # June 2026 vs May 2026
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-07-01",
        period_b_from="2026-05-01",
        period_b_to="2026-06-01",
    )
    assert result["period_a"]["start"] == "2026-06-01"
    assert result["period_b"]["start"] == "2026-05-01"


@patch("spectra.chat.insight_tools.get_today_in_user_timezone")
def test_mtd_alignment_truncates_period_b(mock_today, monkeypatch):
    """Ensure that if period_a is partial/unfinished, period_b's end is aligned/truncated."""
    mock_today.return_value = date(2026, 6, 24)
    _patch_rows(monkeypatch, [])
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-06-24",
        period_b_from="2026-05-01",
        period_b_to="2026-06-01",
    )
    assert result["period_a"]["start"] == "2026-06-01"
    assert result["period_a"]["end"] == "2026-06-24"
    assert result["period_b"]["start"] == "2026-05-01"
    assert result["period_b"]["end"] == "2026-05-24"


@patch("spectra.chat.insight_tools.get_today_in_user_timezone")
def test_no_alignment_when_both_full(mock_today, monkeypatch):
    """Ensure no truncation alignment occurs when both periods are in the past and fully completed."""
    mock_today.return_value = date(2026, 6, 24)
    _patch_rows(monkeypatch, [])
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-05-01",
        period_a_to="2026-06-01",
        period_b_from="2026-04-01",
        period_b_to="2026-05-01",
    )
    assert result["period_a"]["end"] == "2026-06-01"
    assert result["period_b"]["end"] == "2026-05-01"


@patch("spectra.chat.insight_tools.get_today_in_user_timezone")
def test_period_b_shorter_than_aligned_adds_limitation(mock_today, monkeypatch):
    """Ensure that if period_b is shorter than the aligned length, no extension occurs and a limitation is added."""
    mock_today.return_value = date(2026, 6, 24)
    _patch_rows(monkeypatch, [])
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-06-24",
        period_b_from="2026-05-15",
        period_b_to="2026-05-20",
    )
    assert result["period_b"]["end"] == "2026-05-20"
    assert any("skewed" in lim for lim in result["limitations"])


def test_delta_pct_label_new_spending(monkeypatch):
    """Ensure delta_pct_label is 'new_spending' when period_b spend is 0 and period_a spend is positive."""
    rows = [
        ("2026-06-10", "Grab", -150_000, "Transport", ""),
    ]
    _patch_rows(monkeypatch, rows)
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-07-01",
        period_b_from="2026-05-01",
        period_b_to="2026-06-01",
    )
    assert result["totals"]["spent_delta_pct"] is None
    assert result["totals"]["spent_delta_pct_label"] == "new_spending"
    assert result["category_deltas"][0]["delta_pct_label"] == "new_spending"


def test_delta_pct_label_stopped_spending(monkeypatch):
    """Ensure delta_pct is -100.0 and delta_pct_label is 'stopped_spending' when period_a spend is 0 and period_b spend is positive."""
    rows = [
        ("2026-05-10", "Grab", -150_000, "Transport", ""),
    ]
    _patch_rows(monkeypatch, rows)
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-07-01",
        period_b_from="2026-05-01",
        period_b_to="2026-06-01",
    )
    assert result["totals"]["spent_delta_pct"] == -100.0
    assert result["totals"]["spent_delta_pct_label"] == "stopped_spending"
    assert result["category_deltas"][0]["delta_pct_label"] == "stopped_spending"


def test_delta_pct_label_no_activity(monkeypatch):
    """Ensure delta_pct_label is 'no_activity' when both periods have 0 spend."""
    _patch_rows(monkeypatch, [])
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-07-01",
        period_b_from="2026-05-01",
        period_b_to="2026-06-01",
    )
    assert result["totals"]["spent_delta_pct"] is None
    assert result["totals"]["spent_delta_pct_label"] == "no_activity"


@patch("spectra.chat.insight_tools.get_today_in_user_timezone")
def test_default_periods_are_mtd_aligned(mock_today, monkeypatch):
    """Ensure default periods are Month-to-Date (MTD) aligned when no args are provided."""
    mock_today.return_value = date(2026, 6, 24)
    _patch_rows(monkeypatch, [])
    result = compare_period_spending("user-1")
    assert result["period_a"]["start"] == "2026-06-01"
    assert result["period_a"]["end"] == "2026-06-25"
    assert result["period_b"]["start"] == "2026-05-01"
    assert result["period_b"]["end"] == "2026-05-25"


from spectra.chat.insight_tools import get_today_in_user_timezone
@patch("spectra.chat.insight_tools.datetime")
def test_timezone_uses_ho_chi_minh_not_utc(mock_dt):
    """Ensure the user timezone (Asia/Ho_Chi_Minh) is used to resolve 'today' rather than server UTC date."""
    def now_side_effect(tz=None):
        utc_dt = datetime(2026, 6, 24, 17, 0, 0, tzinfo=timezone.utc)
        if tz is not None:
            return utc_dt.astimezone(tz)
        return utc_dt
    mock_dt.now.side_effect = now_side_effect
    result = get_today_in_user_timezone()
    assert result == date(2026, 6, 25)


@patch("spectra.chat.insight_tools.get_today_in_user_timezone")
def test_partial_period_boundary_end_equals_today(mock_today):
    """Boundary test: end_date == today is considered partial (since end date is exclusive)."""
    mock_today.return_value = date(2026, 6, 24)
    from spectra.chat.insight_tools import _is_partial_period
    assert _is_partial_period(date(2026, 6, 1), date(2026, 6, 24), date(2026, 6, 24)) is True


@patch("spectra.chat.insight_tools.get_today_in_user_timezone")
def test_full_period_boundary_end_is_tomorrow(mock_today):
    """Boundary test: end_date == today + 1 is considered full/finished (exclusive convention)."""
    mock_today.return_value = date(2026, 6, 24)
    from spectra.chat.insight_tools import _is_partial_period
    assert _is_partial_period(date(2026, 6, 1), date(2026, 6, 25), date(2026, 6, 24)) is False


def test_delta_pct_label_normal(monkeypatch):
    """Ensure delta_pct_label is 'normal' when both periods have positive spending."""
    rows = [
        ("2026-06-10", "Grab", -150_000, "Transport", ""),
        ("2026-05-10", "Grab", -100_000, "Transport", ""),
    ]
    _patch_rows(monkeypatch, rows)
    result = compare_period_spending(
        "user-1",
        period_a_from="2026-06-01",
        period_a_to="2026-07-01",
        period_b_from="2026-05-01",
        period_b_to="2026-06-01",
    )
    assert result["totals"]["spent_delta_pct"] == 50.0
    assert result["totals"]["spent_delta_pct_label"] == "normal"
    assert result["category_deltas"][0]["delta_pct_label"] == "normal"

