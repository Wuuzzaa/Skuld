"""Covered Calls router - PowerOptions-style ITM covered call screener."""

from fastapi import APIRouter, Depends, Query
import pandas as pd

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_covered_calls(
    expiration_date: str,
    delta_target: float = 0.6,
    max_per_symbol: int = 3,
    min_open_interest: int = 100,
    min_annualized: float = 0.0,
    min_downside: float = 0.0,
    min_volume: int = 0,
    earnings_filter: bool = False,
    above_ma20: bool = False,
    above_ma50: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Calculate covered calls for given parameters."""
    params = {
        "expiration_date": expiration_date,
        "delta_target": delta_target,
        "max_per_symbol": max_per_symbol,
        "min_open_interest": min_open_interest,
        "min_annualized": min_annualized,
        "min_downside": min_downside,
        "min_volume": min_volume,
        "earnings_filter": earnings_filter,
        "above_ma20": above_ma20,
        "above_ma50": above_ma50,
    }

    cached = cache.get("covered_calls", params)
    if cached is not None:
        return cached

    # Query raw data
    sql_params = {
        "expiration_date": expiration_date,
        "delta_target": delta_target,
        "max_per_symbol": max_per_symbol,
        "min_open_interest": min_open_interest,
    }
    df = query_sql_file("covered_calls.sql", sql_params)

    if df.empty:
        return []

    # Import calculation from existing src
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.covered_call_calculation import calc_covered_calls, get_page_covered_calls

    # Calculate metrics
    cc_df = calc_covered_calls(df)

    if cc_df.empty:
        return []

    # Apply filters
    cc_df = get_page_covered_calls(
        cc_df,
        min_annualized=min_annualized / 100,  # Convert from percentage
        min_downside=min_downside / 100,
        earnings_buffer_days=5 if earnings_filter else -9999,
        above_ma20=above_ma20,
        above_ma50=above_ma50,
        min_volume=min_volume,
    )

    if cc_df.empty:
        return []

    # Convert percentages for frontend display
    for col in ['assigned_return', 'annualized_return', 'downside_protection', 'moneyness']:
        if col in cc_df.columns:
            cc_df[col] = cc_df[col] * 100

    result = df_to_json_safe(cc_df)
    cache.set("covered_calls", params, result, ttl=300)
    return result
