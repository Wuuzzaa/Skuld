"""
UniverseSpec + Universe resolver.

Two modes (both V1):
- static:  fixed symbol list
- dynamic: filter + rank + top-N, rebalanced daily/weekly/monthly
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, Literal

import pandas as pd


RebalanceMode = Literal["daily", "weekly", "monthly"]


@dataclass
class UniverseFilter:
    """
    Declarative filter for the dynamic universe.

    criteria: list of simple predicate expressions on filter fields
              (evaluated as pandas.query strings), e.g.
              ["iv_rank > 30", "market_cap > 10e9", "sector == 'Technology'"]
    rank_by:  field name to rank by (descending)
    top_n:    keep this many top-ranked symbols
    """

    criteria: list[str] = field(default_factory=list)
    rank_by: Optional[str] = None
    top_n: int = 20


@dataclass
class UniverseSpec:
    """
    User-facing universe declaration. Consumed by the frontend and by
    `resolve_universe(spec, snapshot_date, ...)`.
    """

    mode: Literal["static", "dynamic"] = "static"
    symbols: list[str] = field(default_factory=list)
    filter: Optional[UniverseFilter] = None
    rebalance: RebalanceMode = "daily"

    def validate(self) -> list[str]:
        issues: list[str] = []
        if self.mode == "static" and not self.symbols:
            issues.append("static universe must have at least one symbol")
        if self.mode == "dynamic" and self.filter is None:
            issues.append("dynamic universe requires a UniverseFilter")
        return issues


class Universe:
    """
    Runtime universe resolver — memoizes per-date symbol lists to avoid
    re-evaluating the filter every day when rebalance is weekly/monthly.
    """

    def __init__(self, spec: UniverseSpec):
        self.spec = spec
        self._cache: dict[date, list[str]] = {}
        self._last_rebalance: Optional[date] = None
        self._last_symbols: list[str] = []

    def resolve(
        self,
        snapshot_date: date,
        stocks_frame: Optional[pd.DataFrame] = None,
    ) -> list[str]:
        """
        Return the active universe for `snapshot_date`.

        For static mode: always returns `spec.symbols` unchanged.
        For dynamic mode: on rebalance-day, evaluates the filter against
        `stocks_frame` (a DataFrame keyed by symbol with filter fields as
        columns); on non-rebalance days, returns the previously resolved list.
        """
        if self.spec.mode == "static":
            return list(self.spec.symbols)

        if snapshot_date in self._cache:
            return list(self._cache[snapshot_date])

        if self._is_rebalance_day(snapshot_date) or self._last_rebalance is None:
            if stocks_frame is None or stocks_frame.empty:
                symbols = []
            else:
                symbols = self._apply_filter(stocks_frame)
            self._last_rebalance = snapshot_date
            self._last_symbols = symbols
        else:
            symbols = list(self._last_symbols)

        self._cache[snapshot_date] = list(symbols)
        return symbols

    def _is_rebalance_day(self, d: date) -> bool:
        mode = self.spec.rebalance
        if mode == "daily":
            return True
        if self._last_rebalance is None:
            return True
        delta = d - self._last_rebalance
        if mode == "weekly":
            return delta >= timedelta(days=7)
        if mode == "monthly":
            return delta >= timedelta(days=28)
        return True

    def _apply_filter(self, frame: pd.DataFrame) -> list[str]:
        filt = self.spec.filter
        if filt is None:
            return []
        df = frame.copy()
        for expr in filt.criteria:
            try:
                df = df.query(expr)
            except Exception:
                # Skip criteria that can't be evaluated (missing column, etc.).
                # Loud logging is done one level up in the loader.
                continue
        if filt.rank_by and filt.rank_by in df.columns:
            df = df.sort_values(filt.rank_by, ascending=False)
        return df.head(filt.top_n).index.tolist()


def resolve_universe(
    spec: UniverseSpec,
    snapshot_date: date,
    stocks_frame: Optional[pd.DataFrame] = None,
) -> list[str]:
    """One-shot convenience wrapper (no caching)."""
    return Universe(spec).resolve(snapshot_date, stocks_frame)
