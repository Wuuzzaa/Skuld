"""Spreads router - credit and debit vertical spreads."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_dataframe, query_sql_file, df_to_json_safe

router = APIRouter()


@router.get("/expirations")
async def get_expirations(current_user: dict = Depends(get_current_user)):
    """Get available expiration dates with DTE."""
    df = query_sql_file("expiration_dte_asc.sql")
    return df_to_json_safe(df)


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
    df = query_sql_file("spreads_input.sql", params)

    if df.empty:
        return []

    # Import calculation from existing src
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.spreads_calculation import get_page_spreads

    spreads_df = get_page_spreads(df, strategy_type=strategy_type, iv_correction="auto")

    return df_to_json_safe(spreads_df)
