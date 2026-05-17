"""Zahltagstrategie Dividend Screener router - Nils Gajovi's 11-point scoring system."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_dividend_screener(
    # Yield filters
    min_yield: float = Query(3.0, ge=0, description="Minimum dividend yield %"),
    max_yield: float = Query(100.0, ge=0, description="Maximum dividend yield %"),
    # Price filters
    min_price: float = Query(10.0, ge=0, description="Minimum stock price"),
    max_price: float = Query(10000.0, ge=0, description="Maximum stock price"),
    # Fundamental filters
    min_market_cap_b: float = Query(0.0, ge=0, description="Minimum market cap in billions"),
    min_avg_volume: int = Query(0, ge=0, description="Minimum average daily volume"),
    max_debt_to_equity: float = Query(0.0, ge=0, description="Max debt/equity ratio (0=no filter)"),
    # Dividend filters
    min_dividend_years: int = Query(0, ge=0, description="Minimum consecutive dividend growth years"),
    only_champions: bool = Query(False, description="Only Dividend Champions (25+ years)"),
    only_contenders_plus: bool = Query(False, description="Only Champions + Contenders (10+ years)"),
    # Technical filters
    below_sma200: bool = Query(False, description="Only stocks trading below 200-day SMA"),
    above_52w_low: bool = Query(False, description="Only stocks >10% above 52-week low"),
    # Other
    sector: str = Query("", description="Filter by sector (empty=all)"),
    exclude_reits: bool = Query(False, description="Exclude Real Estate/REITs"),
    min_score: int = Query(0, ge=0, le=33, description="Minimum total score to show"),
    current_user: dict = Depends(get_current_user),
):
    """Run dividend screener with 11-point scoring matrix.

    Returns scored stocks sorted by total score (max 33 points).
    Recommendations: BUY (>=23), WATCH (12-22), DISCARD (<12).
    """
    cache_params = {
        "min_yield": min_yield, "max_yield": max_yield,
        "min_price": min_price, "max_price": max_price,
        "min_market_cap_b": min_market_cap_b, "min_avg_volume": min_avg_volume,
        "max_debt_to_equity": max_debt_to_equity,
        "min_dividend_years": min_dividend_years,
        "only_champions": only_champions, "only_contenders_plus": only_contenders_plus,
        "below_sma200": below_sma200, "above_52w_low": above_52w_low,
        "sector": sector, "exclude_reits": exclude_reits, "min_score": min_score,
    }

    cached = cache.get("dividend_screener", cache_params)
    if cached is not None:
        return cached

    # Query raw data from the dividend_screener SQL
    df = query_sql_file("dividend_screener.sql")

    if df.empty:
        return {"results": [], "summary": {}}

    # Import scoring and filtering logic
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.dividend_screener import calculate_dividend_scores, filter_dividend_screener

    # Score all stocks
    scored_df = calculate_dividend_scores(df)

    # Apply filters
    filtered_df = filter_dividend_screener(
        scored_df,
        min_yield=min_yield,
        max_yield=max_yield,
        min_price=min_price,
        max_price=max_price,
        min_market_cap_b=min_market_cap_b,
        min_avg_volume=min_avg_volume,
        max_debt_to_equity=max_debt_to_equity,
        min_dividend_years=min_dividend_years,
        min_score=min_score,
        sector=sector,
        below_sma200=below_sma200,
        above_52w_low=above_52w_low,
        only_champions=only_champions,
        only_contenders_plus=only_contenders_plus,
        exclude_reits=exclude_reits,
    )

    # Build summary
    summary = {
        "total_dividend_stocks": len(df),
        "filtered_count": len(filtered_df),
        "buy_count": int((filtered_df['recommendation'] == 'BUY').sum()) if not filtered_df.empty else 0,
        "watch_count": int((filtered_df['recommendation'] == 'WATCH').sum()) if not filtered_df.empty else 0,
        "avg_score": round(float(filtered_df['score_total'].mean()), 1) if not filtered_df.empty else 0,
        "avg_yield": round(float(filtered_df['dividend_yield_pct'].mean()), 2) if not filtered_df.empty else 0,
    }

    # Select columns for response (keep it manageable)
    output_cols = [
        'symbol', 'company_name', 'sector', 'industry', 'price',
        'dividend_yield_pct', 'dividend_growth_years', 'dividend_classification',
        'payout_ratio_pct', 'trailing_pe', 'profit_margin_pct', 'eps_growth_pct',
        'debt_to_equity', 'roe_pct', 'market_cap_b', 'avg_volume',
        'rsi_14', 'pct_from_sma200', 'pct_from_52w_high',
        'short_pct_float', 'analyst_recommendation',
        'score_fundamental', 'score_dividend', 'score_technical', 'score_total',
        'recommendation',
    ]
    existing_cols = [c for c in output_cols if c in filtered_df.columns]

    result = {
        "results": df_to_json_safe(filtered_df[existing_cols]) if not filtered_df.empty else [],
        "summary": summary,
    }

    cache.set("dividend_screener", cache_params, result, ttl=300)
    return result


@router.get("/sectors")
async def get_sectors(current_user: dict = Depends(get_current_user)):
    """Return list of unique sectors for filter dropdown."""
    cached = cache.get("dividend_screener_sectors", {})
    if cached is not None:
        return cached

    df = query_sql_file("dividend_screener.sql")
    if df.empty:
        return []

    sectors = sorted(df['sector'].dropna().unique().tolist())
    cache.set("dividend_screener_sectors", {}, sectors, ttl=3600)
    return sectors
