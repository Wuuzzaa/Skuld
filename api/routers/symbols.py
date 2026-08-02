"""Symbols / Symbol Page router."""

import math

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import query_dataframe, query_sql_file, df_to_json_safe

router = APIRouter()

# Zeitraum → Tage für die Kurshistorie
_RANGE_DAYS = {"1M": 31, "3M": 93, "6M": 186, "1Y": 372, "3Y": 1100}


@router.get("/")
async def list_symbols(current_user: dict = Depends(get_current_user)):
    """Get all available symbols."""
    df = query_dataframe('SELECT DISTINCT symbol FROM "OptionDataMerged" ORDER BY symbol ASC')
    return df["symbol"].tolist()


@router.get("/{symbol}/chart")
async def get_symbol_chart(
    symbol: str,
    range: str = Query("6M", description="1M|3M|6M|1Y|3Y"),
    current_user: dict = Depends(get_current_user),
):
    """Chart-Panel-Daten: Kurshistorie + Expirations (Expected Range + Max Pain).

    - Kurshistorie: OHLCV aus StockPricesYahooHistory (nach Zeitraum gefiltert).
    - Expirations: je Verfall Expected Range (±1σ = Spot·IV·√(DTE/365)) und
      Max Pain (Strike mit minimalem Gesamt-Auszahlung an Optionskäufer,
      aggregiert über Open Interest aller Strikes je contract_type).
    """
    sym = symbol.upper()
    days = _RANGE_DAYS.get(range.upper(), 186)

    # ── Kurshistorie ──────────────────────────────────────────────────────────
    hist = query_dataframe(
        """
        SELECT date AS d, open, high, low, close, volume
        FROM "StockPricesYahooHistory"
        WHERE symbol = :symbol
          AND date > CURRENT_DATE - make_interval(days => :days)
        ORDER BY date ASC
        """,
        {"symbol": sym, "days": days},
    )
    price_history = [
        {"date": str(r["d"])[:10], "close": _f(r["close"]), "volume": _f(r["volume"])}
        for _, r in hist.iterrows()
    ]

    spot = price_history[-1]["close"] if price_history else None

    # ── Optionskette je Verfall → Expected Range + Max Pain ──────────────────
    chain = query_dataframe(
        """
        SELECT expiration_date, days_to_expiration, contract_type,
               strike_price, open_interest, implied_volatility, live_stock_price
        FROM "OptionDataMerged"
        WHERE symbol = :symbol
          AND days_to_expiration > 0
        ORDER BY expiration_date ASC, strike_price ASC
        """,
        {"symbol": sym},
    )
    if spot is None and not chain.empty:
        spot = _f(chain.iloc[0]["live_stock_price"])

    expirations = []
    if not chain.empty:
        for exp, grp in chain.groupby("expiration_date"):
            dte = int(grp["days_to_expiration"].iloc[0])
            # ATM-IV (nächster Strike zum Spot), sonst Median
            atm_iv = _atm_iv(grp, spot)
            exp_move = (
                spot * atm_iv * math.sqrt(dte / 365.0)
                if spot and atm_iv and dte > 0 else None
            )
            expirations.append({
                "expiration_date": str(exp)[:10],
                "dte": dte,
                "iv": round(atm_iv * 100, 1) if atm_iv else None,
                "expected_move": round(exp_move, 2) if exp_move else None,
                "expected_low": round(spot - exp_move, 2) if (spot and exp_move) else None,
                "expected_high": round(spot + exp_move, 2) if (spot and exp_move) else None,
                "max_pain": _max_pain(grp),
            })

    return {
        "symbol": sym,
        "spot": round(spot, 2) if spot else None,
        "range": range.upper(),
        "price_history": price_history,
        "expirations": expirations,
    }


@router.get("/{symbol}")
async def get_symbol_details(symbol: str, current_user: dict = Depends(get_current_user)):
    """Get full details for a specific symbol (Fundamentals / IV / Technicals)."""
    params = {"symbol": symbol.upper()}
    fundamentals = query_sql_file("symbolpage.sql", params)
    iv_history = query_sql_file("iv_history_symbolpage.sql", params)
    technicals = query_sql_file("technical_indicators_one_year_one_symbol.sql", params)
    return {
        "fundamentals": df_to_json_safe(fundamentals),
        "iv_history": df_to_json_safe(iv_history),
        "technicals": df_to_json_safe(technicals),
    }


# ── Helfer ────────────────────────────────────────────────────────────────────
def _f(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _atm_iv(grp, spot):
    """IV der Option mit Strike am nächsten zum Spot."""
    if spot is None:
        vals = [_f(v) for v in grp["implied_volatility"] if _f(v)]
        return sorted(vals)[len(vals) // 2] if vals else None
    best_iv, best_dist = None, None
    for _, r in grp.iterrows():
        iv = _f(r["implied_volatility"])
        k = _f(r["strike_price"])
        if iv is None or k is None:
            continue
        dist = abs(k - spot)
        if best_dist is None or dist < best_dist:
            best_dist, best_iv = dist, iv
    return best_iv


def _max_pain(grp):
    """Strike mit minimaler Gesamt-Auszahlung an Optionskäufer (Max-Pain-Theorie).

    Für jeden Kandidaten-Strike K: Summe über alle Calls max(K-strike,0)*OI (ITM-Calls)
    + alle Puts max(strike-K,0)*OI. Der K mit dem Minimum ist Max Pain.
    """
    strikes = sorted({_f(k) for k in grp["strike_price"] if _f(k) is not None})
    if not strikes:
        return None
    calls = [(_f(r["strike_price"]), _f(r["open_interest"]) or 0)
             for _, r in grp[grp["contract_type"] == "call"].iterrows() if _f(r["strike_price"])]
    puts = [(_f(r["strike_price"]), _f(r["open_interest"]) or 0)
            for _, r in grp[grp["contract_type"] == "put"].iterrows() if _f(r["strike_price"])]
    if not calls and not puts:
        return None

    best_k, best_pay = None, None
    for k in strikes:
        pay = 0.0
        for cs, coi in calls:
            if k > cs:
                pay += (k - cs) * coi
        for ps, poi in puts:
            if k < ps:
                pay += (ps - k) * poi
        if best_pay is None or pay < best_pay:
            best_pay, best_k = pay, k
    return round(best_k, 2) if best_k is not None else None
