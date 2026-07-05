"""
SmartPreloader: Hybrid B+C loading strategy (see backtest.md Kap. 3.3).

Loads all merged option/stock data for the backtest span in a small number
of bulk queries against `getOptionDataMergedHistory(target_date)` and keeps
it in RAM as pandas DataFrames indexed for O(1) snapshot construction.

The preloader is intentionally simple in V1: one big query per date, cached
by date. If your DB has 500 trading days × 100 symbols × 60 strikes × 8 expiries
that becomes ~24M rows — hence `estimate_ram_gb` warns before starting.

V2 will move to columnar Parquet cache + range-scan queries.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from src.backtesting.data.snapshot import (
    MarketSnapshot,
    Option,
    OptionChain,
    StockData,
)

# NOTE: `src.historization` and `src.database` are imported lazily inside
# `_load_merged_frame` so that in-memory/synthetic usage of the framework
# (tests, offline replay) doesn't require sqlalchemy or a live DB.

logger = logging.getLogger(__name__)


SQL_QUERY_DIR = Path(__file__).resolve().parents[3] / "db" / "SQL" / "query" / "backtest"


def _sql_path(name: str) -> str:
    return str(SQL_QUERY_DIR / name)


class SmartPreloader:
    """
    Pulls one merged frame per snapshot date; caches it. Provides
    `get_snapshot(target_date, symbols)` for the engine's main loop.

    All queries live under `db/SQL/query/backtest/` per spec Kap. 13.1.
    """

    def __init__(self, symbols: Optional[list[str]] = None, fields: Optional[list[str]] = None):
        self.symbols = symbols  # None => all symbols in the DB on that date
        self.fields = fields    # None => use a default set of fields
        self._frame_cache: dict[date, pd.DataFrame] = {}

    # ── Public API ────────────────────────────────────────────────────────

    def get_snapshot(
        self, target_date: date, symbols: Optional[list[str]] = None
    ) -> MarketSnapshot:
        """
        Build a MarketSnapshot for `target_date`, restricted to `symbols`
        (or `self.symbols` if omitted).

        The heavy lifting is one SQL call to `getOptionDataMergedHistory`.
        Subsequent calls on the same date reuse the cached raw DataFrame
        (`_frame_cache`) but rebuild the `MarketSnapshot` — sufficient for
        V1 where each day is visited exactly once per backtest.
        """
        frame = self._load_merged_frame(target_date, symbols=symbols)
        active = symbols if symbols is not None else self.symbols

        if active is not None and active:
            frame = frame[frame["symbol"].isin(active)]

        return self._frame_to_snapshot(target_date, frame)

    def prefetch(self, dates: list[date]) -> None:
        """Optional: pull frames for a whole date range up-front."""
        for d in dates:
            self._load_merged_frame(d)

    def clear_cache(self) -> None:
        self._frame_cache.clear()

    # ── Internals ─────────────────────────────────────────────────────────

    def _load_merged_frame(self, target_date: date, symbols: Optional[list[str]] = None) -> pd.DataFrame:
        if target_date in self._frame_cache:
            # Note: We assume that if it's cached, it contains all symbols/fields we need
            # for this session. Usually SmartPreloader is per-backtest.
            return self._frame_cache[target_date]

        t0 = time.time()

        # Build column list
        # Minimum fields required for any backtest
        essential = {"symbol", "live_stock_price"}
        requested = set(self.fields) if self.fields else set()
        
        # If no fields specified, we might want to load a sensible default set
        # or everything if really requested. But the goal is to be dynamic.
        all_cols = essential | requested
        cols_str = ", ".join([f'"{c}"' for c in sorted(all_cols)])

        # Filter by symbols if provided
        active_symbols = symbols if symbols is not None else self.symbols
        where_clause_str = ""
        params = {"target_date": target_date.isoformat()}
        
        if active_symbols:
            where_clause_str = 'WHERE "symbol" IN :symbols'
            params["symbols"] = tuple(active_symbols)

        # Load SQL template
        try:
            template_path = Path(_sql_path("merged_snapshot.sql"))
            sql_template = template_path.read_text(encoding="utf-8")
            sql = sql_template.format(
                columns=cols_str,
                where_clause=where_clause_str
            )
        except Exception as e:
            logger.error("Failed to load SQL template merged_snapshot.sql: %s", e)
            # Fallback to hardcoded query if template fails
            sql = f'SELECT {cols_str} FROM "getOptionDataMergedHistory"(:target_date) {where_clause_str}'
        
        try:
            from src.database import select_into_dataframe

            df = select_into_dataframe(
                query=sql,
                params=params,
                session_variables={"jit": "off", "enable_nestloop": "off"},
            )
        except Exception as e:
            logger.warning(
                "getOptionDataMergedHistory(%s) failed (%s) — returning empty frame",
                target_date,
                e,
            )
            df = pd.DataFrame()

        if df is None:
            df = pd.DataFrame()

        logger.debug(
            "SmartPreloader: loaded %d rows for %s in %.2fs",
            len(df),
            target_date,
            time.time() - t0,
        )
        self._frame_cache[target_date] = df
        return df

    @staticmethod
    def _frame_to_snapshot(target_date: date, df: pd.DataFrame) -> MarketSnapshot:
        snap = MarketSnapshot(date=target_date)
        if df is None or df.empty:
            return snap

        # ── Stocks: one row per symbol (dedup on symbol, take first) ──
        stock_cols_of_interest = [
            "symbol", "day_close", "day_open", "day_high", "day_low",
            "day_volume", "live_stock_price", "iv_rank", "iv_percentile",
            "historical_volatility_30d", "earnings_date", "days_to_earnings",
            "last_dividend", "last_dividend_date", "dividend_growth_years",
            "analyst_mean_target",
        ]
        available_stock_cols = [c for c in stock_cols_of_interest if c in df.columns]
        stock_frame = df[available_stock_cols].drop_duplicates(subset=["symbol"])

        for row in stock_frame.itertuples(index=False):
            row_dict = row._asdict()
            symbol = row_dict.get("symbol")
            if not symbol:
                continue
            snap.stocks[symbol] = StockData(
                symbol=symbol,
                as_of=target_date,
                live_stock_price=_as_float(row_dict.get("live_stock_price")),
                day_open=_as_optional_float(row_dict.get("day_open")),
                day_high=_as_optional_float(row_dict.get("day_high")),
                day_low=_as_optional_float(row_dict.get("day_low")),
                day_close=_as_optional_float(row_dict.get("day_close")),
                day_volume=_as_optional_int(row_dict.get("day_volume")),
                iv_rank=_as_optional_float(row_dict.get("iv_rank")),
                iv_percentile=_as_optional_float(row_dict.get("iv_percentile")),
                historical_volatility_30d=_as_optional_float(
                    row_dict.get("historical_volatility_30d")
                ),
                earnings_date=_as_optional_date(row_dict.get("earnings_date")),
                days_to_earnings=_as_optional_int(row_dict.get("days_to_earnings")),
                last_dividend=_as_optional_float(row_dict.get("last_dividend")),
                last_dividend_date=_as_optional_date(
                    row_dict.get("last_dividend_date")
                ),
                dividend_growth_years=_as_optional_int(
                    row_dict.get("dividend_growth_years")
                ),
                analyst_mean_target=_as_optional_float(
                    row_dict.get("analyst_mean_target")
                ),
            )

        # ── Options: one row per contract; group by symbol ────────────
        for row in df.itertuples(index=False):
            row_dict = row._asdict()
            symbol = row_dict.get("symbol")
            option_osi = row_dict.get("option_osi")
            if not symbol or not option_osi:
                continue

            option = Option(
                symbol=symbol,
                option_osi=option_osi,
                contract_type=str(row_dict.get("contract_type", "")).lower(),
                expiration_date=_as_optional_date(row_dict.get("expiration_date"))
                    or target_date,
                strike=_as_float(row_dict.get("strike_price")),
                day_close=_as_float(row_dict.get("day_close")),
                open_interest=_as_optional_int(row_dict.get("open_interest")) or 0,
                day_volume=_as_optional_int(row_dict.get("day_volume")) or 0,
                implied_volatility=_as_optional_float(
                    row_dict.get("implied_volatility")
                ),
                delta=_as_optional_float(row_dict.get("greeks_delta")),
                gamma=_as_optional_float(row_dict.get("greeks_gamma")),
                theta=_as_optional_float(row_dict.get("greeks_theta")),
                vega=_as_optional_float(row_dict.get("greeks_vega")),
                days_to_expiration=_as_optional_int(
                    row_dict.get("days_to_expiration")
                ) or 0,
                shares_per_contract=_as_optional_int(
                    row_dict.get("shares_per_contract")
                ) or 100,
            )

            chain = snap.chains.get(symbol)
            if chain is None:
                chain = OptionChain(symbol=symbol, as_of=target_date)
                snap.chains[symbol] = chain
            if option.is_call:
                chain.calls.append(option)
            else:
                chain.puts.append(option)

        snap.universe = sorted(snap.stocks.keys())
        return snap


# ── Helpers ──────────────────────────────────────────────────────────────

def _as_float(v) -> float:
    try:
        if v is None or pd.isna(v):
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _as_optional_float(v) -> Optional[float]:
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _as_optional_int(v) -> Optional[int]:
    try:
        if v is None or pd.isna(v):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _as_optional_date(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, date):
        return v
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


# ── RAM estimator (Kap. 3.3) ─────────────────────────────────────────────

def estimate_ram_gb(
    num_symbols: int, num_trading_days: int, avg_contracts_per_symbol: int = 400
) -> float:
    """
    Rough back-of-envelope RAM cost, in gigabytes.

    Assumes ~600 bytes per contract row after pandas overhead.
    """
    rows = num_symbols * num_trading_days * avg_contracts_per_symbol
    return (rows * 600) / (1024**3)
