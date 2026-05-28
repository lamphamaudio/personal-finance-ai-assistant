from __future__ import annotations

from datetime import date

from spectra.cycles import (
    CYCLE_MODE_FIXED,
    CYCLE_MODE_LAST_BUSINESS_DAY,
    cycle_window_for,
    parse_cycle_rule,
    serialize_cycle_rule,
)


def test_cycle_window_uses_previous_last_business_day_before_anchor() -> None:
    start, end = cycle_window_for(date(2026, 5, 15), CYCLE_MODE_LAST_BUSINESS_DAY)
    assert start == date(2026, 4, 30)
    assert end == date(2026, 5, 29)


def test_cycle_window_uses_current_last_business_day_after_anchor() -> None:
    start, end = cycle_window_for(date(2026, 5, 30), CYCLE_MODE_LAST_BUSINESS_DAY)
    assert start == date(2026, 5, 29)
    assert end == date(2026, 6, 30)


def test_parse_cycle_rule_clamps_legacy_numeric_days() -> None:
    assert parse_cycle_rule("31", clamp_legacy_day=True) == (CYCLE_MODE_FIXED, 28)
    assert serialize_cycle_rule(CYCLE_MODE_FIXED, 28) == "fixed:28"

