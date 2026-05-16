"""Correlation Matrix router."""

from fastapi import APIRouter, Depends, Query
from typing import Optional
import pandas as pd
import numpy as np

from api.core.auth import get_current_user
from api.core.database import query_dataframe, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/symbols")
async def get_available_symbols(
    current_user: dict = Depends(get_current_user),
):
    """Get all symbols that have historical price data."""
    cached = cache.get("correlation_symbols")
    if cached is not None:
        return cached

    sql = """
        SELECT DISTINCT symbol
        FROM "StockPricesYahooHistoryDaily"
        WHERE snapshot_date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY symbol
    """
    df = query_dataframe(sql)
    result = df["symbol"].tolist()
    cache.set("correlation_symbols", None, result, ttl=3600)
    return result


@router.get("/")
async def get_correlation_matrix(
    symbols: str = Query(..., description="Comma-separated list of symbols"),
    lookback_days: int = Query(252, description="Lookback period in trading days (252=1Y, 126=6M, 63=3M)"),
    method: str = Query("pearson", description="Correlation method: pearson, spearman, kendall"),
    current_user: dict = Depends(get_current_user),
):
    """Calculate correlation matrix from daily returns."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    if len(symbol_list) < 2:
        return {"matrix": [], "symbols": [], "stats": {}}

    params = {"symbols": symbol_list, "lookback_days": str(lookback_days)}
    cache_key = f"{symbols}_{lookback_days}_{method}"

    cached = cache.get("correlation_matrix", {"key": cache_key})
    if cached is not None:
        return cached

    sql = """
        SELECT symbol, snapshot_date, close
        FROM "StockPricesYahooHistoryDaily"
        WHERE symbol = ANY(:symbols)
          AND snapshot_date >= CURRENT_DATE - CAST(:lookback_days || ' days' AS INTERVAL)
        ORDER BY symbol, snapshot_date
    """
    df = query_dataframe(sql, params)

    if df.empty:
        return {"matrix": [], "symbols": [], "stats": {}}

    # Pivot to wide format: dates as index, symbols as columns
    pivot = df.pivot(index="snapshot_date", columns="symbol", values="close")

    # Drop symbols with insufficient data (< 80% of max available days)
    min_data_points = int(pivot.shape[0] * 0.8)
    pivot = pivot.dropna(axis=1, thresh=min_data_points)

    # Forward-fill gaps, then calculate daily returns
    pivot = pivot.ffill()
    returns = pivot.pct_change().dropna()

    if returns.empty or returns.shape[1] < 2:
        return {"matrix": [], "symbols": [], "stats": {}}

    # Calculate correlation matrix
    corr = returns.corr(method=method)

    # Build response
    available_symbols = corr.columns.tolist()
    matrix_data = []
    for i, sym1 in enumerate(available_symbols):
        for j, sym2 in enumerate(available_symbols):
            val = corr.iloc[i, j]
            if not np.isnan(val):
                matrix_data.append({
                    "x": sym1,
                    "y": sym2,
                    "value": round(float(val), 4),
                })

    # Summary stats
    # Get upper triangle values (exclude diagonal)
    upper_tri = corr.where(np.triu(np.ones(corr.shape), k=1).astype(bool))
    flat_values = upper_tri.values.flatten()
    flat_values = flat_values[~np.isnan(flat_values)]

    stats = {
        "avg_correlation": round(float(np.mean(flat_values)), 4) if len(flat_values) > 0 else 0,
        "max_correlation": round(float(np.max(flat_values)), 4) if len(flat_values) > 0 else 0,
        "min_correlation": round(float(np.min(flat_values)), 4) if len(flat_values) > 0 else 0,
        "num_symbols": len(available_symbols),
        "num_data_points": int(returns.shape[0]),
        "date_from": str(returns.index.min()),
        "date_to": str(returns.index.max()),
    }

    # Find top correlated and least correlated pairs
    pairs = []
    for i in range(len(available_symbols)):
        for j in range(i + 1, len(available_symbols)):
            val = corr.iloc[i, j]
            if not np.isnan(val):
                pairs.append({
                    "pair": f"{available_symbols[i]} / {available_symbols[j]}",
                    "correlation": round(float(val), 4),
                })

    pairs_sorted = sorted(pairs, key=lambda x: x["correlation"], reverse=True)
    top_correlated = pairs_sorted[:10]
    least_correlated = pairs_sorted[-10:][::-1]

    result = {
        "matrix": matrix_data,
        "symbols": available_symbols,
        "stats": stats,
        "top_correlated": top_correlated,
        "least_correlated": least_correlated,
    }

    cache.set("correlation_matrix", {"key": cache_key}, result, ttl=600)
    return result
