"""Dividend Portfolio Builder router - Build optimized dividend portfolios for target income."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def build_portfolio(
    target_monthly_eur: float = Query(100.0, ge=10, le=10000, description="Target monthly dividend in EUR"),
    eur_usd_rate: float = Query(1.08, ge=0.5, le=2.0, description="EUR/USD exchange rate"),
    max_positions: int = Query(20, ge=5, le=40, description="Maximum portfolio positions"),
    max_per_sector: int = Query(2, ge=1, le=5, description="Maximum stocks per sector"),
    min_score: int = Query(18, ge=1, le=33, description="Minimum score from 11-point matrix"),
    min_yield_pct: float = Query(2.5, ge=0, le=20, description="Minimum dividend yield %"),
    min_price: float = Query(10.0, ge=0, description="Minimum stock price"),
    max_single_position_pct: float = Query(10.0, ge=3, le=50, description="Max % investment in single stock"),
    current_user: dict = Depends(get_current_user),
):
    """Build optimized dividend portfolio for target monthly income.

    Uses 11-point scoring matrix results + payment cycle diversification to
    create a portfolio that pays dividends every month.
    """
    cache_params = {
        "target_monthly_eur": target_monthly_eur,
        "eur_usd_rate": eur_usd_rate,
        "max_positions": max_positions,
        "max_per_sector": max_per_sector,
        "min_score": min_score,
        "min_yield_pct": min_yield_pct,
        "min_price": min_price,
        "max_single_position_pct": max_single_position_pct,
    }

    cached = cache.get("dividend_portfolio_builder", cache_params)
    if cached is not None:
        return cached

    # Query candidates with payment cycle info
    df = query_sql_file("dividend_portfolio_builder.sql")

    if df.empty:
        return {"portfolio": [], "summary": {}, "monthly_breakdown": []}

    # Score all candidates using the dividend screener scoring
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.dividend_screener import calculate_dividend_scores
    from src.dividend_portfolio_builder import build_dividend_portfolio

    # Score candidates
    scored_df = calculate_dividend_scores(df)

    # Build portfolio
    result = build_dividend_portfolio(
        candidates_df=scored_df,
        target_monthly_eur=target_monthly_eur,
        eur_usd_rate=eur_usd_rate,
        max_positions=max_positions,
        max_per_sector=max_per_sector,
        min_score=min_score,
        min_yield_pct=min_yield_pct,
        min_price=min_price,
        max_single_position_pct=max_single_position_pct,
    )

    cache.set("dividend_portfolio_builder", cache_params, result, ttl=300)
    return result
