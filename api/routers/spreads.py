"""Spreads router - credit and debit vertical spreads."""

from fastapi import APIRouter, Depends, Query
import pandas as pd

from api.core.auth import get_current_user
from api.core.database import query_dataframe, query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/expirations")
async def get_expirations(current_user: dict = Depends(get_current_user)):
    """Get available expiration dates with DTE, day of week, and expiration type."""
    cached = cache.get("expirations")
    if cached is not None:
        return cached

    df = query_sql_file("expiration_dte_asc.sql")

    if not df.empty:
        # Add day of week and expiration type classification
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from src.utils.option_utils import get_expiration_type

        df['expiration_date'] = pd.to_datetime(df['expiration_date'])
        df['day_of_week'] = df['expiration_date'].dt.strftime('%A')
        df['expiration_type'] = df['expiration_date'].apply(get_expiration_type)

    result = df_to_json_safe(df)
    cache.set("expirations", None, result, ttl=600)  # 10 min cache
    return result


@router.get("/")
async def get_spreads(
    expiration_date: str,
    option_type: str = "put",
    delta_target: float = 0.2,
    spread_width: int = 5,
    strategy_type: str = "credit",
    min_open_interest: int = 100,
    min_day_volume: int = 20,
    min_iv_rank: int = 0,
    min_iv_percentile: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Calculate spreads for given parameters. Returns raw data from SQL + Python calculation."""
    params = {
        "expiration_date": expiration_date,
        "option_type": option_type,
        "delta_target": delta_target,
        "spread_width": spread_width,
        "strategy_type": strategy_type,
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile,
    }

    cached = cache.get("spreads", params)
    if cached is not None:
        return cached

    df = query_sql_file("spreads_input.sql", params)

    if df.empty:
        return []

    # Import calculation from existing src
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.spreads_calculation import get_page_spreads

    spreads_df = get_page_spreads(df, strategy_type=strategy_type, iv_correction="auto")

    result = df_to_json_safe(spreads_df)
    cache.set("spreads", params, result, ttl=300)  # 5 min cache
    return result
