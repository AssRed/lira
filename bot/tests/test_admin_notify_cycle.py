"""Tests for the admin questionnaire's cycle/period date-range output."""
from __future__ import annotations

from datetime import date

from bot.services.admin_notify import _format_cycle_window, _ru_date


def test_ru_date_uses_genitive_month_names() -> None:
    assert _ru_date(date(2026, 3, 5)) == "5 марта 2026"
    assert _ru_date(date(2026, 1, 1)) == "1 января 2026"
    assert _ru_date(date(2026, 12, 31)) == "31 декабря 2026"


def test_cycle_window_renders_both_period_and_full_cycle() -> None:
    period, cycle = _format_cycle_window(
        last_period_start=date(2026, 3, 5),
        cycle_length_days=28,
        period_length_days=5,
    )
    # Period window covers 5 days: 5..9 March (last_period_start inclusive).
    assert period == "5 марта 2026 — 9 марта 2026"
    # Full cycle spans 28 days from 5 March -> day before next period.
    # 5 March + 27 days = 1 April, so the cycle window is 5 March..1 April.
    assert cycle == "5 марта 2026 — 1 апреля 2026"


def test_cycle_window_handles_missing_fields_gracefully() -> None:
    period, cycle = _format_cycle_window(None, 28, 5)
    assert period is None
    assert cycle is None

    period, cycle = _format_cycle_window(date(2026, 3, 5), None, None)
    assert period is None
    assert cycle is None

    period, cycle = _format_cycle_window(date(2026, 3, 5), 28, None)
    assert period is None
    assert cycle == "5 марта 2026 — 1 апреля 2026"

    period, cycle = _format_cycle_window(date(2026, 3, 5), None, 5)
    assert period == "5 марта 2026 — 9 марта 2026"
    assert cycle is None


def test_cycle_window_clamps_one_day_period_to_start_date() -> None:
    """A 1-day period shouldn't render as an empty range."""
    period, _ = _format_cycle_window(date(2026, 3, 5), 28, 1)
    assert period == "5 марта 2026 — 5 марта 2026"
    # 0 / negative lengths are treated as missing data — the admin
    # message will fall back to the legacy days-only line.
    period, _ = _format_cycle_window(date(2026, 3, 5), 28, 0)
    assert period is None
