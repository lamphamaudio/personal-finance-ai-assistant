"""Month-to-month financial cycles.

Spectra supports two cycle anchors:

* a fixed day of the month (1-28)
* the last business day of the month (Mon-Fri only)

A cycle runs from one anchor date to the day before the next month's anchor.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta


DEFAULT_CYCLE_START_DAY = 1
MIN_CYCLE_START_DAY = 1
MAX_CYCLE_START_DAY = 28
CYCLE_MODE_FIXED = "fixed"
CYCLE_MODE_LAST_BUSINESS_DAY = "last_business_day"
VALID_CYCLE_MODES = {CYCLE_MODE_FIXED, CYCLE_MODE_LAST_BUSINESS_DAY}
DEFAULT_CYCLE_RULE = f"{CYCLE_MODE_FIXED}:{DEFAULT_CYCLE_START_DAY}"


def normalize_cycle_start_day(value: int) -> int:
    """Clamp and validate the start day (1-28)."""
    v = int(value)
    if not MIN_CYCLE_START_DAY <= v <= MAX_CYCLE_START_DAY:
        raise ValueError(
            f"cycle_start_day must be between {MIN_CYCLE_START_DAY} and {MAX_CYCLE_START_DAY}"
        )
    return v


def normalize_cycle_mode(value: str) -> str:
    """Validate the cycle mode identifier."""
    mode = str(value or "").strip().lower()
    if mode not in VALID_CYCLE_MODES:
        raise ValueError(f"cycle_mode must be one of: {', '.join(sorted(VALID_CYCLE_MODES))}")
    return mode


def parse_cycle_rule(
    value: int | str | None,
    *,
    clamp_legacy_day: bool = False,
) -> tuple[str, int | None]:
    """Parse a stored cycle rule into ``(mode, fixed_day)``.

    Accepted values:
      * ``14`` or ``"14"``             -> ``("fixed", 14)``
      * ``"fixed:14"``                 -> ``("fixed", 14)``
      * ``"last_business_day"``        -> ``("last_business_day", None)``
    """
    if value is None or str(value).strip() == "":
        return CYCLE_MODE_FIXED, DEFAULT_CYCLE_START_DAY

    if isinstance(value, int):
        return CYCLE_MODE_FIXED, normalize_cycle_start_day(value)

    raw = str(value).strip().lower()
    if raw == CYCLE_MODE_LAST_BUSINESS_DAY:
        return CYCLE_MODE_LAST_BUSINESS_DAY, None

    if raw.startswith(f"{CYCLE_MODE_FIXED}:"):
        raw = raw.split(":", 1)[1].strip()

    try:
        day = int(raw)
    except ValueError as exc:
        raise ValueError(f"invalid cycle rule: {value}") from exc

    if clamp_legacy_day:
        day = max(MIN_CYCLE_START_DAY, min(day, MAX_CYCLE_START_DAY))
    else:
        day = normalize_cycle_start_day(day)
    return CYCLE_MODE_FIXED, day


def serialize_cycle_rule(mode: str, fixed_day: int | None = None) -> str:
    """Serialize a cycle preference to the DB/API format."""
    normalized_mode = normalize_cycle_mode(mode)
    if normalized_mode == CYCLE_MODE_LAST_BUSINESS_DAY:
        return CYCLE_MODE_LAST_BUSINESS_DAY
    day = DEFAULT_CYCLE_START_DAY if fixed_day is None else normalize_cycle_start_day(fixed_day)
    return f"{CYCLE_MODE_FIXED}:{day}"


def parse_iso_date(value: str) -> date:
    """Parse an ISO-8601 date string."""
    return date.fromisoformat(value)


# ── month arithmetic ──────────────────────────────────────────────

def _add_months(year: int, month: int, n: int) -> tuple[int, int]:
    """Add *n* months (can be negative) to (year, month)."""
    m = year * 12 + (month - 1) + n
    return divmod(m, 12)[0], divmod(m, 12)[1] + 1


def _fixed_day_anchor(year: int, month: int, start_day: int) -> date:
    """Resolve the anchor for a fixed monthly day."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(start_day, last))


def _last_business_day_anchor(year: int, month: int) -> date:
    """Resolve the last Monday-Friday of a month."""
    day = calendar.monthrange(year, month)[1]
    candidate = date(year, month, day)
    while candidate.weekday() >= 5:
        candidate -= timedelta(days=1)
    return candidate


def _anchor(year: int, month: int, cycle_rule: int | str) -> date:
    """Resolve the anchor date for a given cycle rule."""
    mode, fixed_day = parse_cycle_rule(cycle_rule)
    if mode == CYCLE_MODE_LAST_BUSINESS_DAY:
        return _last_business_day_anchor(year, month)
    return _fixed_day_anchor(year, month, fixed_day or DEFAULT_CYCLE_START_DAY)


# ── public API ────────────────────────────────────────────────────

def cycle_start_for(ref: date, cycle_rule: int | str) -> date:
    """Return the start date of the cycle that contains *ref*."""
    anchor = _anchor(ref.year, ref.month, cycle_rule)
    if ref >= anchor:
        return anchor
    # ref is before this month's anchor → previous month's anchor
    py, pm = _add_months(ref.year, ref.month, -1)
    return _anchor(py, pm, cycle_rule)


def next_cycle_start(cycle_start: date, cycle_rule: int | str) -> date:
    """Return the first day of the next cycle after *cycle_start*."""
    ny, nm = _add_months(cycle_start.year, cycle_start.month, 1)
    return _anchor(ny, nm, cycle_rule)


def cycle_window_for(ref: date, cycle_rule: int | str) -> tuple[date, date]:
    """Return ``(start, end_exclusive)`` for the cycle containing *ref*."""
    start = cycle_start_for(ref, cycle_rule)
    return start, next_cycle_start(start, cycle_rule)


def cycle_key_for(ref: date, cycle_rule: int | str) -> str:
    """Stable sort-key for the cycle containing *ref*."""
    return cycle_start_for(ref, cycle_rule).isoformat()


def format_cycle_label(start: date, end_exclusive: date) -> str:
    """Human-readable label: ``'25 Feb 2026 -> 24 Mar 2026'``."""
    end_inclusive = end_exclusive - timedelta(days=1)
    return f"{start.strftime('%d %b %Y')} -> {end_inclusive.strftime('%d %b %Y')}"
