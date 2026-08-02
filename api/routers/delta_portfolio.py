"""Delta Portfolio router — read-only lookups for the Delta Portfolio Tracker page.

Mirrors the DB access of the master Streamlit `delta_portfolio.py`. All positions
are held client-side (browser state); this router only provides live market data:
option delta, stock prices (batch), sectors, and concrete OTM put hedge candidates.
No schema, no writes — read-only queries only.
"""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_dataframe, df_to_json_safe

router = APIRouter()


@router.get("/option-delta")
async def get_option_delta(
    symbol: str = Query(...),
    strike: float = Query(...),
    expiry: str = Query(..., description="YYYY-MM-DD"),
    contract_type: str = Query(..., pattern="^(call|put)$"),
    current_user: dict = Depends(get_current_user),
):
    """Live greeks_delta for one specific option (OptionDataMassive)."""
    df = query_dataframe(
        """
        SELECT greeks_delta
        FROM "OptionDataMassive"
        WHERE symbol = :symbol
          AND strike_price = :strike
          AND expiration_date = :expiry
          AND contract_type = :ctype
        LIMIT 1
        """,
        {"symbol": symbol, "strike": strike, "expiry": expiry, "ctype": contract_type},
    )
    if df.empty or df.iloc[0]["greeks_delta"] is None:
        return {"delta": None}
    val = df.iloc[0]["greeks_delta"]
    try:
        return {"delta": float(val)}
    except (TypeError, ValueError):
        return {"delta": None}


@router.get("/stock-price")
async def get_stock_price(
    symbols: str = Query(..., description="Comma-separated symbols, e.g. AAPL,SPY"),
    current_user: dict = Depends(get_current_user),
):
    """Latest close per symbol (StockPricesYahoo). Batch to avoid N+1 requests.

    Returns {symbol: price|null} for every requested symbol.
    """
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    result: dict[str, float | None] = {s: None for s in syms}
    if not syms:
        return result

    placeholders = ", ".join(f":s{i}" for i in range(len(syms)))
    params = {f"s{i}": s for i, s in enumerate(syms)}
    df = query_dataframe(
        f"""
        SELECT symbol, close
        FROM "StockPricesYahoo"
        WHERE symbol IN ({placeholders})
        """,
        params,
    )
    for _, row in df.iterrows():
        try:
            result[str(row["symbol"]).upper()] = float(row["close"])
        except (TypeError, ValueError):
            pass
    return result


@router.get("/sectors")
async def get_sectors(
    symbols: str = Query(..., description="Comma-separated symbols"),
    current_user: dict = Depends(get_current_user),
):
    """Sector per symbol (StockAssetProfilesYahoo). Returns {symbol: sector}."""
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    result: dict[str, str] = {}
    if not syms:
        return result

    placeholders = ", ".join(f":s{i}" for i in range(len(syms)))
    params = {f"s{i}": s for i, s in enumerate(syms)}
    df = query_dataframe(
        f"""
        SELECT symbol, sector
        FROM "StockAssetProfilesYahoo"
        WHERE symbol IN ({placeholders})
        """,
        params,
    )
    for _, row in df.iterrows():
        sec = row["sector"]
        result[str(row["symbol"]).upper()] = str(sec) if sec is not None else "Unbekannt"
    return result


@router.get("/hedge-candidates")
async def get_hedge_candidates(
    symbol: str = Query(...),
    stock_price: float = Query(..., gt=0),
    current_user: dict = Depends(get_current_user),
):
    """Liquid OTM put hedge candidates from OptionDataMerged.

    Mirrors the Streamlit query: puts with strike 82–97% of spot, DTE 25–95,
    open interest >= 100, premium >= 0.20; nearest expiry / highest |delta| first.
    """
    df = query_dataframe(
        """
        SELECT
            symbol,
            strike_price,
            expiration_date,
            days_to_expiration,
            ROUND(premium_option_price::numeric, 2)    AS praemie,
            ROUND(greeks_delta::numeric, 3)             AS delta,
            ROUND(implied_volatility::numeric * 100, 1) AS iv_pct,
            ROUND(iv_rank::numeric, 1)                  AS iv_rank,
            open_interest                               AS oi
        FROM "OptionDataMerged"
        WHERE symbol = :symbol
          AND contract_type = 'put'
          AND strike_price BETWEEN :strike_lo AND :strike_hi
          AND days_to_expiration BETWEEN 25 AND 95
          AND open_interest >= 100
          AND premium_option_price >= 0.20
        ORDER BY days_to_expiration ASC, ABS(greeks_delta) DESC
        LIMIT 8
        """,
        {
            "symbol": symbol,
            "strike_lo": round(stock_price * 0.82, 2),
            "strike_hi": round(stock_price * 0.97, 2),
        },
    )
    return df_to_json_safe(df)
