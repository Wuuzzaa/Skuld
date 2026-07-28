"""Married Put Analysis router."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_married_puts(
    strike_multiplier: float = 1.2,
    min_roi: float = 3.0,
    max_roi: float = 7.0,
    min_days: int = 30,
    max_days: int = 500,
    max_results: int = 50,
    current_user: dict = Depends(get_current_user),
):
    """Get married put analysis with dividend growth stocks."""
    all_params = {
        "strike_multiplier": strike_multiplier,
        "min_roi": min_roi,
        "max_roi": max_roi,
        "min_days": min_days,
        "max_days": max_days,
        "max_results": max_results,
    }

    cached = cache.get("married_puts", all_params)
    if cached is not None:
        return cached

    df = query_sql_file("married_put.sql", {"strike_multiplier": strike_multiplier})

    if df.empty:
        return []

    # Apply filters
    df = df[
        (df["roi_annualized_pct"] >= min_roi)
        & (df["roi_annualized_pct"] <= max_roi)
        & (df["days_to_expiration"] >= min_days)
        & (df["days_to_expiration"] <= max_days)
    ]

    df = df.head(max_results)

    result = df_to_json_safe(df)
    cache.set("married_puts", all_params, result, ttl=300)
    return result


class MarriedPutBacktestRequest(BaseModel):
    symbol: str
    live_stock_price: float
    premium_option_price: float
    number_of_stocks: int
    option_osi: str | None = None
    strike_price: float
    expiration_date: str
    entry_date: str
    compare_date: str


@router.post("/backtest")
async def backtest_married_put(
    request: MarriedPutBacktestRequest,
    current_user: dict = Depends(get_current_user),
):
    """Time-travel exit simulation for a married put position."""
    params = request.model_dump()

    cached = cache.get("married_put_backtest", params)
    if cached is not None:
        return cached

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.married_put_backtest import simulate_married_put_exit

    trade = {
        "symbol": request.symbol,
        "live_stock_price": request.live_stock_price,
        "premium_option_price": request.premium_option_price,
        "number_of_stocks": request.number_of_stocks,
        "option_osi": request.option_osi,
        "strike_price": request.strike_price,
        "expiration_date": request.expiration_date,
    }
    result = simulate_married_put_exit(trade, request.entry_date, request.compare_date)

    cache.set("married_put_backtest", params, result, ttl=300)
    return result
