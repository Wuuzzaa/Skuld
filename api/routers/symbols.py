"""Symbols / Symbol Page router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_dataframe, query_sql_file

router = APIRouter()


@router.get("/")
async def list_symbols(current_user: dict = Depends(get_current_user)):
    """Get all available symbols."""
    df = query_dataframe('SELECT DISTINCT symbol FROM "OptionDataMerged" ORDER BY symbol ASC')
    return df["symbol"].tolist()


@router.get("/{symbol}")
async def get_symbol_details(symbol: str, current_user: dict = Depends(get_current_user)):
    """Get full details for a specific symbol."""
    params = {"symbol": symbol.upper()}

    fundamentals = query_sql_file("symbolpage.sql", params)
    iv_history = query_sql_file("iv_history_symbolpage.sql", params)
    technicals = query_sql_file("technical_indicators_one_year_one_symbol.sql", params)

    for df in [fundamentals, iv_history, technicals]:
        for col in df.select_dtypes(include=["datetime64"]).columns:
            df[col] = df[col].astype(str)

    return {
        "fundamentals": fundamentals.to_dict(orient="records"),
        "iv_history": iv_history.to_dict(orient="records"),
        "technicals": technicals.to_dict(orient="records"),
    }
