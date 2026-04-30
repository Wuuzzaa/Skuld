"""Multifactor Swingtrading router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe

router = APIRouter()


@router.get("/")
async def get_multifactor_swingtrading(
    top_percentile_value_score: float = Query(20, ge=1, le=100),
    top_n: int = Query(50, ge=1, le=500),
    drop_missing_values: bool = False,
    drop_weak_value_factors: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """Calculate multifactor swingtrading candidates using value scoring."""
    df = query_sql_file("multifactor_swingtrading.sql")

    if df.empty:
        return []

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.multifactor_swingtrading_strategy import calculate_multifactor_swingtrading_strategy

    result_df = calculate_multifactor_swingtrading_strategy(
        df,
        top_percentile_value_score=top_percentile_value_score,
        top_n=top_n,
        drop_missing_values=drop_missing_values,
        drop_weak_value_factors=drop_weak_value_factors,
    )

    return df_to_json_safe(result_df)
