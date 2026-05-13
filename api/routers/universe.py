"""Universe router — enriched symbol list with metadata."""

from fastapi import APIRouter, Depends

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_universe(current_user: dict = Depends(get_current_user)):
    """Get full universe of symbols with enriched metadata and S&P 500 flag."""
    cached = cache.get("universe", None)
    if cached is not None:
        return cached

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.sp500_constituents import SP500_SYMBOLS

    sp500_set = set(SP500_SYMBOLS)

    df = query_sql_file("universe.sql")

    if df.empty:
        return {"symbols": [], "meta": {}}

    df["is_sp500"] = df["symbol"].isin(sp500_set)

    symbols = df_to_json_safe(df)

    sectors = sorted(df["sector"].dropna().unique().tolist())
    industries = sorted(df["industry"].dropna().unique().tolist())
    exchanges = sorted(df["exchange"].dropna().unique().tolist())

    result = {
        "symbols": symbols,
        "meta": {
            "total": len(symbols),
            "sp500_count": int(df["is_sp500"].sum()),
            "sectors": sectors,
            "industries": industries,
            "exchanges": exchanges,
        },
    }

    cache.set("universe", None, result, ttl=300)
    return result
