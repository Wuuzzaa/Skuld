"""Symbols / Symbol Page router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_dataframe, query_sql_file, df_to_json_safe

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

    return {
        "fundamentals": df_to_json_safe(fundamentals),
        "iv_history": df_to_json_safe(iv_history),
        "technicals": df_to_json_safe(technicals),
    }
