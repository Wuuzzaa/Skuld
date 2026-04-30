"""Married Put Analysis router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe

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

    return df_to_json_safe(df)
