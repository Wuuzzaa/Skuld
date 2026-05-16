"""Correlation Matrix router."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
import pandas as pd
import numpy as np

from api.core.auth import get_current_user
from api.core.database import query_dataframe, df_to_json_safe
from api.core import cache

router = APIRouter()

MAX_SYMBOLS = 50  # Hard cap to prevent timeouts


class MatrixRequest(BaseModel):
    symbols: List[str]
    lookback_days: int = 252
    method: str = "pearson"


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


@router.post("/matrix")
async def post_correlation_matrix(
    body: MatrixRequest,
    current_user: dict = Depends(get_current_user),
):
    """Calculate correlation matrix from daily returns (POST for large symbol lists)."""
    symbol_list = [s.strip().upper() for s in body.symbols if s.strip()]
    return _calculate_matrix(symbol_list, body.lookback_days, body.method)


@router.get("/")
async def get_correlation_matrix(
    symbols: str = Query(..., description="Comma-separated list of symbols"),
    lookback_days: int = Query(252, description="Lookback period in trading days (252=1Y, 126=6M, 63=3M)"),
    method: str = Query("pearson", description="Correlation method: pearson, spearman, kendall"),
    current_user: dict = Depends(get_current_user),
):
    """Calculate correlation matrix from daily returns."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    return _calculate_matrix(symbol_list, lookback_days, method)


def _calculate_matrix(symbol_list: list, lookback_days: int, method: str):
    """Shared correlation matrix calculation."""
    if len(symbol_list) < 2:
        return {"matrix": [], "symbols": [], "stats": {}, "capped": False}

    # Cap to prevent server overload
    capped = len(symbol_list) > MAX_SYMBOLS
    if capped:
        symbol_list = symbol_list[:MAX_SYMBOLS]

    params = {"symbols": symbol_list, "lookback_days": str(lookback_days)}
    cache_key = f"{'_'.join(sorted(symbol_list))}_{lookback_days}_{method}"

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
        return {"matrix": [], "symbols": [], "stats": {}, "capped": capped}

    # Pivot to wide format: dates as index, symbols as columns
    pivot = df.pivot(index="snapshot_date", columns="symbol", values="close")

    # Drop symbols with insufficient data (< 80% of max available days)
    min_data_points = int(pivot.shape[0] * 0.8)
    pivot = pivot.dropna(axis=1, thresh=min_data_points)

    # Forward-fill gaps, then calculate daily returns
    pivot = pivot.ffill()
    returns = pivot.pct_change().dropna()

    if returns.empty or returns.shape[1] < 2:
        return {"matrix": [], "symbols": [], "stats": {}, "capped": capped}

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
        "capped": capped,
        "max_symbols": MAX_SYMBOLS,
    }

    cache.set("correlation_matrix", {"key": cache_key}, result, ttl=600)
    return result


@router.get("/pair-detail")
async def get_pair_detail(
    symbol_a: str = Query(..., description="First symbol"),
    symbol_b: str = Query(..., description="Second symbol"),
    lookback_days: int = Query(252, description="Lookback period in trading days"),
    method: str = Query("pearson", description="Correlation method"),
    current_user: dict = Depends(get_current_user),
):
    """Get detailed correlation data for a specific pair: prices, returns, rolling correlation."""
    sym_a = symbol_a.strip().upper()
    sym_b = symbol_b.strip().upper()

    cache_key = f"{sym_a}_{sym_b}_{lookback_days}_{method}"
    cached = cache.get("correlation_pair_detail", {"key": cache_key})
    if cached is not None:
        return cached

    params = {"symbols": [sym_a, sym_b], "lookback_days": str(lookback_days)}
    sql = """
        SELECT symbol, snapshot_date, close
        FROM "StockPricesYahooHistoryDaily"
        WHERE symbol = ANY(:symbols)
          AND snapshot_date >= CURRENT_DATE - CAST(:lookback_days || ' days' AS INTERVAL)
        ORDER BY symbol, snapshot_date
    """
    df = query_dataframe(sql, params)

    if df.empty or df["symbol"].nunique() < 2:
        return {"error": "Insufficient data for one or both symbols"}

    pivot = df.pivot(index="snapshot_date", columns="symbol", values="close")
    pivot = pivot.ffill().dropna()

    if pivot.shape[0] < 10:
        return {"error": "Not enough overlapping data points"}

    returns = pivot.pct_change().dropna()

    # Overall correlation
    if method == "pearson":
        corr_value = float(returns[sym_a].corr(returns[sym_b]))
    elif method == "spearman":
        corr_value = float(returns[sym_a].corr(returns[sym_b], method="spearman"))
    else:
        corr_value = float(returns[sym_a].corr(returns[sym_b], method="kendall"))

    # Rolling correlation (30-day window)
    rolling_corr = returns[sym_a].rolling(window=30).corr(returns[sym_b])
    rolling_data = []
    for date, val in rolling_corr.dropna().items():
        rolling_data.append({"date": str(date)[:10], "value": round(float(val), 4)})

    # Price series (normalized to 100 at start for comparison)
    prices_a = pivot[sym_a]
    prices_b = pivot[sym_b]
    norm_a = (prices_a / prices_a.iloc[0]) * 100
    norm_b = (prices_b / prices_b.iloc[0]) * 100

    price_data = []
    for date in pivot.index:
        price_data.append({
            "date": str(date)[:10],
            "price_a": round(float(prices_a[date]), 2),
            "price_b": round(float(prices_b[date]), 2),
            "norm_a": round(float(norm_a[date]), 2),
            "norm_b": round(float(norm_b[date]), 2),
        })

    # Returns scatter data (for scatter plot)
    scatter_data = []
    for date in returns.index:
        scatter_data.append({
            "date": str(date)[:10],
            "return_a": round(float(returns[sym_a][date]) * 100, 4),
            "return_b": round(float(returns[sym_b][date]) * 100, 4),
        })

    # Summary statistics
    stats = {
        "correlation": round(corr_value, 4),
        "method": method,
        "data_points": int(returns.shape[0]),
        "date_from": str(returns.index.min())[:10],
        "date_to": str(returns.index.max())[:10],
        "symbol_a": {
            "symbol": sym_a,
            "mean_return": round(float(returns[sym_a].mean()) * 100, 4),
            "std_return": round(float(returns[sym_a].std()) * 100, 4),
            "total_return": round(float((prices_a.iloc[-1] / prices_a.iloc[0] - 1) * 100), 2),
            "start_price": round(float(prices_a.iloc[0]), 2),
            "end_price": round(float(prices_a.iloc[-1]), 2),
        },
        "symbol_b": {
            "symbol": sym_b,
            "mean_return": round(float(returns[sym_b].mean()) * 100, 4),
            "std_return": round(float(returns[sym_b].std()) * 100, 4),
            "total_return": round(float((prices_b.iloc[-1] / prices_b.iloc[0] - 1) * 100), 2),
            "start_price": round(float(prices_b.iloc[0]), 2),
            "end_price": round(float(prices_b.iloc[-1]), 2),
        },
        "rolling_30d_avg": round(float(rolling_corr.dropna().mean()), 4),
        "rolling_30d_min": round(float(rolling_corr.dropna().min()), 4),
        "rolling_30d_max": round(float(rolling_corr.dropna().max()), 4),
    }

    result = {
        "stats": stats,
        "prices": price_data,
        "returns_scatter": scatter_data,
        "rolling_correlation": rolling_data,
    }

    cache.set("correlation_pair_detail", {"key": cache_key}, result, ttl=600)
    return result
