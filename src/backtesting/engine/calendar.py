"""
Trading-calendar helpers.

V1 default: use `exchange_calendars` (NYSE) if available; fall back to a
simple weekday filter otherwise. The fallback is good enough for backtests
that don't need pinpoint holiday accuracy — but for production reporting
you should install exchange_calendars.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


def trading_days(start: date, end: date) -> list[date]:
    """
    Return the list of NYSE trading days in [start, end], inclusive.

    Uses `exchange_calendars` when present; otherwise Mon-Fri without
    holidays.
    """
    try:
        import exchange_calendars as xcals  # type: ignore

        cal = xcals.get_calendar("XNYS")
        sessions = cal.sessions_in_range(start.isoformat(), end.isoformat())
        return [ts.date() for ts in sessions]
    except Exception as e:
        logger.debug("exchange_calendars unavailable (%s) — using weekday fallback", e)
        return _weekday_range(start, end)


def _weekday_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    d = start
    while d <= end:
        # Mon=0, Sat=5, Sun=6
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days
