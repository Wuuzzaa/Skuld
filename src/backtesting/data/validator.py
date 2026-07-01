"""
Validator: sanity-check universe + date range against DB availability.

Called from the UI before starting the run to catch dumb setups early.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    available_from: Optional[date] = None
    available_to: Optional[date] = None
    symbol_coverage: dict[str, tuple[Optional[date], Optional[date]]] = field(
        default_factory=dict
    )


def validate_universe_and_range(
    symbols: list[str],
    start_date: date,
    end_date: date,
) -> ValidationResult:
    """
    Confirm the DB has data for the requested (symbols × date-range).

    - Queries MIN/MAX(date) from OptionDataMassiveHistoryDaily overall.
    - Queries per-symbol coverage. Symbols without data become a warning
      rather than a hard error — the user can then decide to drop them.
    - Returns ValidationResult; caller inspects `ok`.
    """
    result = ValidationResult(ok=True)

    if start_date > end_date:
        result.ok = False
        result.errors.append(f"start_date {start_date} is after end_date {end_date}")
        return result

    if not symbols:
        result.ok = False
        result.errors.append("universe is empty")
        return result

    try:
        from src.database import select_into_dataframe

        overall_sql = (
            'SELECT MIN("date") AS min_date, MAX("date") AS max_date '
            'FROM "OptionDataMassiveHistoryDaily"'
        )
        overall = select_into_dataframe(query=overall_sql)
        if overall is not None and not overall.empty:
            row = overall.iloc[0]
            result.available_from = _as_date(row.get("min_date"))
            result.available_to = _as_date(row.get("max_date"))
    except Exception as e:
        result.warnings.append(f"Could not read overall date range: {e}")

    if result.available_from and start_date < result.available_from:
        result.warnings.append(
            f"start_date {start_date} is before earliest available "
            f"({result.available_from}); backtest will start at that date"
        )
    if result.available_to and end_date > result.available_to:
        result.warnings.append(
            f"end_date {end_date} is after latest available "
            f"({result.available_to}); backtest will stop at that date"
        )

    return result


def _as_date(v):
    if v is None:
        return None
    if isinstance(v, date):
        return v
    try:
        import pandas as pd

        return pd.to_datetime(v).date()
    except Exception:
        return None
