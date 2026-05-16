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
    # PowerOptions filters
    macd_positive: bool = False,
    rsi_below_70: bool = False,
    min_eps_growth: float = 0.0,
    max_pe_ratio: float = 0.0,
    max_recommendation: float = 0.0,
    min_avg_volume: int = 0,
    min_market_cap: float = 0.0,
    exclude_biotech: bool = False,
    exclude_leveraged: bool = False,
    max_iv_hv_ratio: float = 0.0,
    # Monthly Picks filters
    min_itm_pct: float = 0.0,
    min_stock_price: float = 0.0,
    max_stock_price: float = 0.0,
    min_premium: float = 0.0,
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
        "macd_positive": macd_positive,
        "rsi_below_70": rsi_below_70,
        "min_eps_growth": min_eps_growth,
        "max_pe_ratio": max_pe_ratio,
        "max_recommendation": max_recommendation,
        "min_avg_volume": min_avg_volume,
        "min_market_cap": min_market_cap,
        "exclude_biotech": exclude_biotech,
        "exclude_leveraged": exclude_leveraged,
        "max_iv_hv_ratio": max_iv_hv_ratio,
        "min_itm_pct": min_itm_pct,
        "min_stock_price": min_stock_price,
        "max_stock_price": max_stock_price,
        "min_premium": min_premium,
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

    # Apply filters (convert percentage inputs from frontend)
    cc_df = get_page_covered_calls(
        cc_df,
        min_annualized=min_annualized / 100 if min_annualized > 0 else 0,
        min_downside=min_downside / 100 if min_downside > 0 else 0,
        earnings_buffer_days=5 if earnings_filter else -9999,
        above_ma20=above_ma20,
        above_ma50=above_ma50,
        min_volume=min_volume,
        # PowerOptions
        macd_positive=macd_positive,
        rsi_below_70=rsi_below_70,
        min_eps_growth=min_eps_growth if min_eps_growth > 0 else None,
        max_pe_ratio=max_pe_ratio if max_pe_ratio > 0 else None,
        max_recommendation=max_recommendation if max_recommendation > 0 else None,
        min_avg_volume=int(min_avg_volume) if min_avg_volume > 0 else None,
        min_market_cap=min_market_cap if min_market_cap > 0 else None,
        exclude_biotech=exclude_biotech,
        exclude_leveraged=exclude_leveraged,
        max_iv_hv_ratio=max_iv_hv_ratio if max_iv_hv_ratio > 0 else None,
        # Monthly Picks
        min_itm_pct=min_itm_pct / 100.0 if min_itm_pct > 0 else None,
        min_stock_price=min_stock_price if min_stock_price > 0 else None,
        max_stock_price=max_stock_price if max_stock_price > 0 else None,
        min_premium=min_premium if min_premium > 0 else None,
    )

    if cc_df.empty:
        return []

    result = df_to_json_safe(cc_df)
    cache.set("covered_calls", params, result, ttl=300)
    return result
