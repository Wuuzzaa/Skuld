"""RSL Momentum Rotation router."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.auth import get_current_user
from api.core.database import query_sql_file
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_rsl_momentum(
    top_n: int = Query(5, ge=1, le=50),
    max_per_sector: int = Query(2, ge=1, le=10),
    exit_percentile: float = Query(50.0, ge=1.0, le=90.0),
    current_user: dict = Depends(get_current_user),
):
    """Calculate RSL Momentum Rotation ranking for S&P 500."""
    cache_params = {
        "top_n": top_n,
        "max_per_sector": max_per_sector,
        "exit_percentile": exit_percentile,
    }

    cached = cache.get("rsl_momentum", cache_params)
    if cached is not None:
        return cached

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.sp500_constituents import SP500_SYMBOLS
    from src.rsl_momentum_strategy import calculate_rsl_momentum_ranking

    df = query_sql_file("rsl_momentum.sql", params={"symbols": list(SP500_SYMBOLS)})

    if df.empty:
        return {"ranking": [], "top_picks": [], "summary": {}}

    result = calculate_rsl_momentum_ranking(
        df,
        top_n=top_n,
        max_per_sector=max_per_sector,
        exit_percentile=exit_percentile,
    )

    cache.set("rsl_momentum", cache_params, result, ttl=300)
    return result


class RslBacktestRequest(BaseModel):
    start_date: str
    end_date: str
    start_budget: float = 10000.0
    flat_fee: float = 4.90
    pct_fee: float = 0.001
    top_n: int = 5
    max_per_sector: int = 2
    exit_percentile: float = 50.0
    trading_frequency: str = "monthly"
    fractional_shares: bool = False
    risk_free_rate: float = 0.0
    tax_rate: float = 0.25


@router.post("/backtest")
async def backtest_rsl_momentum(
    request: RslBacktestRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run the RSL Momentum rotation portfolio backtest simulation."""
    params = request.model_dump()

    cached = cache.get("rsl_backtest", params)
    if cached is not None:
        return cached

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.rsl_momentum_backtest import calculate_rsl_momentum_strategy

    result = calculate_rsl_momentum_strategy(
        start_date=request.start_date,
        end_date=request.end_date,
        start_budget=request.start_budget,
        flat_fee=request.flat_fee,
        pct_fee=request.pct_fee,
        top_n=request.top_n,
        max_per_sector=request.max_per_sector,
        exit_percentile=request.exit_percentile,
        trading_frequency=request.trading_frequency,
        allow_fractional=request.fractional_shares,
        risk_free_rate=request.risk_free_rate,
        tax_rate=request.tax_rate,
    )

    if result is None:
        return {"summary": {}, "equity_curve": [], "transactions": []}

    cache.set("rsl_backtest", params, result, ttl=300)
    return result
