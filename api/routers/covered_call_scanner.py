"""Covered Call Scanner router - ITM covered call screener (PowerOptions MorningUpdate style).

Distinct from the covered_calls router: this scans for the single optimal ITM call
per symbol (closest to a delta target) and ranks by annualized return, mirroring the
master Streamlit `covered_call_scanner` page. Coarse filters run in SQL; the remaining
range filters are applied on the resulting DataFrame (same as the Streamlit page).
"""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_covered_call_scanner(
    dte_min: int = Query(20, ge=0, le=400),
    dte_max: int = Query(60, ge=0, le=400),
    delta_target: float = Query(0.80, ge=0.0, le=1.0),
    delta_target_max: float = Query(1.0, ge=0.0, le=1.0),
    min_annualized: float = Query(0.0, ge=0.0),
    max_annualized: float = Query(0.0, ge=0.0),
    min_market_cap_b: float = Query(1.0, ge=0.0),
    min_oi: int = Query(50, ge=0),
    min_downside: float = Query(0.0, ge=0.0),
    price_min: float = Query(10.0, ge=0.0),
    price_max: float = Query(500.0, ge=0.0),
    min_iv_rank: float = Query(0.0, ge=0.0),
    min_premium: float = Query(0.0, ge=0.0),
    current_user: dict = Depends(get_current_user),
):
    """Scan for optimal ITM covered calls, ranked by annualized return."""
    params = {
        "dte_min": dte_min,
        "dte_max": dte_max,
        "delta_target": delta_target,
        "delta_target_max": delta_target_max,
        "min_annualized": min_annualized,
        "max_annualized": max_annualized,
        "min_market_cap_b": min_market_cap_b,
        "min_oi": min_oi,
        "min_downside": min_downside,
        "price_min": price_min,
        "price_max": price_max,
        "min_iv_rank": min_iv_rank,
        "min_premium": min_premium,
    }

    cached = cache.get("covered_call_scanner", params)
    if cached is not None:
        return cached

    # Coarse filters run in SQL (matches covered_call_scanner.sql named params).
    sql_params = {
        "delta_target": delta_target,
        "dte_min": dte_min,
        "dte_max": dte_max,
        "min_oi": min_oi,
        "min_market_cap": min_market_cap_b * 1e9,
    }
    df = query_sql_file("covered_call_scanner.sql", sql_params)

    if df.empty:
        return []

    # Remaining range filters applied on the DataFrame, mirroring the Streamlit page.
    if delta_target_max < 1.0:
        df = df[df["delta"] <= delta_target_max]
    if min_annualized > 0:
        df = df[df["annualized_return_pct"] >= min_annualized]
    if max_annualized > 0:
        df = df[df["annualized_return_pct"] <= max_annualized]
    if min_downside > 0:
        df = df[df["downside_protection_pct"] >= min_downside]
    if price_min > 0:
        df = df[df["stock_price"] >= price_min]
    if price_max > 0:
        df = df[df["stock_price"] <= price_max]
    if min_iv_rank > 0:
        df = df[df["iv_rank"] >= min_iv_rank]
    if min_premium > 0:
        df = df[df["premium"] >= min_premium]

    if df.empty:
        return []

    result = df_to_json_safe(df)
    cache.set("covered_call_scanner", params, result, ttl=300)
    return result
