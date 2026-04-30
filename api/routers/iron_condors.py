"""Iron Condors router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe
from api.core import cache

router = APIRouter()


@router.get("/")
async def get_iron_condors(
    expiration_date_put: str,
    expiration_date_call: str,
    delta_put: float = 0.15,
    delta_call: float = 0.15,
    width_put: int = 5,
    width_call: int = 5,
    min_open_interest: int = 100,
    min_day_volume: int = 20,
    min_iv_rank: int = 0,
    min_iv_percentile: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Calculate iron condors from put and call spreads."""
    all_params = {
        "expiration_date_put": expiration_date_put,
        "expiration_date_call": expiration_date_call,
        "delta_put": delta_put,
        "delta_call": delta_call,
        "width_put": width_put,
        "width_call": width_call,
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile,
    }

    cached = cache.get("iron_condors", all_params)
    if cached is not None:
        return cached

    common_params = {
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile,
    }

    put_params = {
        **common_params,
        "expiration_date": expiration_date_put,
        "option_type": "put",
        "delta_target": delta_put,
        "spread_width": width_put,
    }
    call_params = {
        **common_params,
        "expiration_date": expiration_date_call,
        "option_type": "call",
        "delta_target": delta_call,
        "spread_width": width_call,
    }

    put_df = query_sql_file("iron_condor_input.sql", put_params)
    call_df = query_sql_file("iron_condor_input.sql", call_params)

    if put_df.empty or call_df.empty:
        return []

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.iron_condor_calculation import calc_iron_condors, get_page_iron_condors

    ic_df = calc_iron_condors(put_df, call_df, iv_correction="auto")
    ic_df = get_page_iron_condors(ic_df)

    result = df_to_json_safe(ic_df)
    cache.set("iron_condors", all_params, result, ttl=300)
    return result
