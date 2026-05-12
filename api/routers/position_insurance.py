"""Position Insurance Tool router."""

import pandas as pd
from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_sql_file, df_to_json_safe

router = APIRouter()


@router.get("/")
async def get_position_insurance(
    symbol: str,
    cost_basis: float = 100.0,
    current_user: dict = Depends(get_current_user),
):
    """Get options data for position insurance (protective puts + optional collar)."""
    params = {
        "symbol": symbol.upper(),
        "today": pd.Timestamp.now().strftime("%Y-%m-%d"),
    }
    df = query_sql_file("position_insurance.sql", params)

    if df.empty:
        return {"puts": [], "calls": [], "current_price": None}

    current_price = float(df["live_stock_price"].iloc[0])
    puts = df[df["contract_type"] == "put"].copy()
    calls = df[df["contract_type"] == "call"].copy()

    return {
        "puts": df_to_json_safe(puts),
        "calls": df_to_json_safe(calls),
        "current_price": current_price,
    }
