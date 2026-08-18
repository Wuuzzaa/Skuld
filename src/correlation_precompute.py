"""Correlation precompute job.

Computes pairwise correlations of daily returns across all symbols with
sufficient recent price history and stores them in "CorrelationPrecomputed",
so the API can serve "symbol vs all" instantly instead of computing live.

Run via: python main.py --mode correlation_precompute
(wired into main.py's task_map / job dispatcher).

No Streamlit / no framework imports — pure computation + DB write.
"""

import logging

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.database import get_postgres_engine, select_into_dataframe

logger = logging.getLogger(__name__)

# Which (lookback, method) combinations to precompute. The API reads whichever
# combination the user selected; keep this in sync with the UI's options.
LOOKBACKS = [63, 126, 252]
METHODS = ["pearson"]

TABLE = '"CorrelationPrecomputed"'


def _load_prices(lookback_days: int) -> pd.DataFrame:
    """Wide price frame (dates x symbols) for symbols with recent data."""
    return select_into_dataframe(
        query="""
            SELECT symbol, snapshot_date, close
            FROM "StockPricesYahooHistoryDaily"
            WHERE snapshot_date >= CURRENT_DATE - CAST(:lookback_days || ' days' AS INTERVAL)
              AND symbol IN (
                SELECT DISTINCT symbol FROM "StockPricesYahooHistoryDaily"
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '30 days'
              )
            ORDER BY symbol, snapshot_date
        """,
        params={"lookback_days": str(lookback_days)},
    )


def _compute_pairs(df: pd.DataFrame, method: str) -> pd.DataFrame:
    """Return long-format correlation pairs (base, peer, correlation)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["base_symbol", "peer_symbol", "correlation"])

    pivot = df.pivot(index="snapshot_date", columns="symbol", values="close")
    min_data_points = int(pivot.shape[0] * 0.8)
    pivot = pivot.dropna(axis=1, thresh=min_data_points).ffill()
    returns = pivot.pct_change().dropna()
    if returns.empty or returns.shape[1] < 2:
        return pd.DataFrame(columns=["base_symbol", "peer_symbol", "correlation"])

    corr = returns.corr(method=method)
    # Long format, excluding self-correlations. Rename axes first so the
    # stack/reset_index doesn't collide with the "symbol" column name.
    corr.index.name = "base_symbol"
    corr.columns.name = "peer_symbol"
    long = corr.stack().reset_index()
    long.columns = ["base_symbol", "peer_symbol", "correlation"]
    long = long[long["base_symbol"] != long["peer_symbol"]]
    long = long[~long["correlation"].isna()]
    long["correlation"] = long["correlation"].round(4)
    return long


def precompute_correlations() -> None:
    """Compute and persist correlations for all LOOKBACKS x METHODS."""
    engine = get_postgres_engine()
    total = 0
    for lookback in LOOKBACKS:
        df = _load_prices(lookback)
        for method in METHODS:
            pairs = _compute_pairs(df, method)
            if pairs.empty:
                logger.warning(
                    "correlation_precompute: no pairs for lookback=%s method=%s", lookback, method
                )
                continue
            pairs["lookback_days"] = lookback
            pairs["method"] = method

            with engine.begin() as conn:
                # Replace this (lookback, method) slice atomically.
                conn.execute(
                    text(f'DELETE FROM {TABLE} WHERE lookback_days = :lb AND method = :m'),
                    {"lb": lookback, "m": method},
                )
                pairs.to_sql(
                    "CorrelationPrecomputed",
                    con=conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=5000,
                )
            total += len(pairs)
            logger.info(
                "correlation_precompute: stored %s pairs (lookback=%s, method=%s)",
                len(pairs), lookback, method,
            )
    logger.info("correlation_precompute: done, %s pairs total", total)
