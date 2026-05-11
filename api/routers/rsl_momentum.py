"""RSL Momentum Rotation router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_rsl_momentum(
    top_n: int = Query(5, ge=1, le=50),
    max_per_sector: int = Query(2, ge=1, le=10),
    exit_percentile: float = Query(50.0, ge=10.0, le=90.0),
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

    df = query_sql_file("rsl_momentum.sql", params={"symbols": tuple(SP500_SYMBOLS)})

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
