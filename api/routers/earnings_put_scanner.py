"""Earnings Put Scanner router — IV-crush strategy around earnings."""

from fastapi import APIRouter, Depends

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_earnings_candidates(
    days_ahead: int = 7,
    current_user: dict = Depends(get_current_user),
):
    cache_key = {"days_ahead": days_ahead}
    cached = cache.get("earnings_put_candidates", cache_key)
    if cached is not None:
        return cached

    df = query_sql_file("earnings_put_scanner.sql", {"days_ahead": days_ahead})
    if df.empty:
        return []

    result = df_to_json_safe(df)
    cache.set("earnings_put_candidates", cache_key, result, ttl=300)
    return result


@router.get("/puts")
async def get_earnings_put_options(
    symbol: str,
    min_oi: int = 50,
    current_user: dict = Depends(get_current_user),
):
    cache_key = {"symbol": symbol, "min_oi": min_oi}
    cached = cache.get("earnings_put_options", cache_key)
    if cached is not None:
        return cached

    df = query_sql_file("earnings_put_candidates.sql", {"symbol": symbol, "min_oi": min_oi})
    if df.empty:
        return []

    result = df_to_json_safe(df)
    cache.set("earnings_put_options", cache_key, result, ttl=300)
    return result
