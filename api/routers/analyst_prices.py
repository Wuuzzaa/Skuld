"""Analyst Prices router."""

from fastapi import APIRouter, Depends

from api.core.auth import get_current_user
from api.core.database import query_sql_file

router = APIRouter()


@router.get("/")
async def get_analyst_prices(current_user: dict = Depends(get_current_user)):
    """Get analyst price targets vs current prices."""
    df = query_sql_file("analyst_prices.sql")
    df = df.rename(columns={
        "close": "price",
        "analyst_mean_target": "mean_analyst_target",
        "target-close$": "difference_dollar",
        "target-close%": "difference_percent",
    })
    return df.to_dict(orient="records")
