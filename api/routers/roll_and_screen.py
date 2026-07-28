"""Roll & Screen router — cash-secured put screener, put/spread rollers, put browser.

Ports master's pages/roll_and_screen.py to FastAPI. This router exposes one
endpoint group per Streamlit tab. The heavy lifting (9-criteria put scoring,
roll ladder math, LLM ranking) already lives in src/ (put_screener,
roll_support_calc, spread_roll_calc, put_ai_ranker) — the endpoints are thin
wrappers that load data via SQL and delegate to that logic.
"""

import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.core.auth import get_current_user
from api.core.database import query_sql_file, query_dataframe, df_to_json_safe
from api.core import cache

# Make the shared src/ package importable (same pattern as other routers).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

router = APIRouter()


# ---------------------------------------------------------------------------
# Tab 1 — Put Screener (9-criteria scoring + shortlist)
# ---------------------------------------------------------------------------
@router.get("/screener")
async def put_screener(
    dte_min: int = Query(20, ge=0, le=400),
    dte_max: int = Query(60, ge=0, le=400),
    price_min: float = Query(10.0, ge=0.0),
    price_max: float = Query(500.0, ge=0.0),
    min_oi: int = Query(50, ge=0),
    min_vol: int = Query(0, ge=0),
    min_premium_share: float = Query(0.0, ge=0.0),
    min_market_cap: float = Query(1e9, ge=0.0),
    pe_max: float = Query(40.0, ge=0.0),
    min_score: int = Query(0, ge=0, le=9),
    current_user: dict = Depends(get_current_user),
):
    """Screen cash-secured put candidates and score them (0-9)."""
    params = {
        "dte_min": dte_min, "dte_max": dte_max, "price_min": price_min,
        "price_max": price_max, "min_oi": min_oi, "min_vol": min_vol,
        "min_premium_share": min_premium_share, "min_market_cap": min_market_cap,
        "pe_max": pe_max, "min_score": min_score,
    }
    cached = cache.get("roll_screener", params)
    if cached is not None:
        return cached

    sql_params = {
        "dte_min": dte_min, "dte_max": dte_max, "price_min": price_min,
        "price_max": price_max, "min_oi": min_oi, "min_vol": min_vol,
        "min_premium_share": min_premium_share, "min_market_cap": min_market_cap,
    }
    df = query_sql_file("put_screener.sql", sql_params)
    if df.empty:
        return []

    from src.put_screener import score_candidates, shortlist_score

    scored = score_candidates(df, pe_max=pe_max)
    scored["shortlist_score"] = scored.apply(shortlist_score, axis=1)
    scored = scored.sort_values(["shortlist_score", "score"], ascending=[False, False]).reset_index(drop=True)

    if min_score > 0:
        scored = scored[scored["score"] >= min_score]

    result = df_to_json_safe(scored)
    cache.set("roll_screener", params, result, ttl=300)
    return result


class ScoreBreakdownRequest(BaseModel):
    """A single scored candidate row (as returned by /screener)."""
    row: dict
    pe_max: float = 40.0


@router.post("/screener/breakdown")
async def screener_breakdown(
    request: ScoreBreakdownRequest,
    current_user: dict = Depends(get_current_user),
):
    """Return the per-criterion score breakdown for one candidate."""
    from src.put_screener import score_breakdown, criterion_labels
    breakdown = score_breakdown(request.row, pe_max=request.pe_max)
    return {"labels": criterion_labels(), "breakdown": breakdown}


class AiRankRequest(BaseModel):
    puts: list[dict]
    max_candidates: int = 25
    provider: str = "deepseek"
    web_search: bool = False


@router.post("/screener/ai-rank")
async def screener_ai_rank(
    request: AiRankRequest,
    current_user: dict = Depends(get_current_user),
):
    """Rank screened put candidates via the configured LLM provider.

    Requires the provider API key to be set in the backend environment
    (DEEPSEEK_API_KEY / KIMI_AI). Returns the markdown ranking + metadata.
    """
    import pandas as pd
    from src.put_ai_ranker import rank_puts, LLMProviderError

    if not request.puts:
        return {"ranking": "", "meta": {}, "error": "no_candidates"}

    puts_df = pd.DataFrame(request.puts)
    try:
        ranking, meta = rank_puts(
            puts_df,
            max_candidates=request.max_candidates,
            provider=request.provider,
            web_search=request.web_search,
        )
    except LLMProviderError as e:
        return {"ranking": "", "meta": {}, "error": "llm_error", "message": str(e)}

    return {"ranking": ranking, "meta": meta}


# ---------------------------------------------------------------------------
# Shared price helpers (ported from master's _current_put_price /
# _current_stock_price — inline SQL, no dedicated .sql file exists).
# ---------------------------------------------------------------------------
def _current_put_price(option_osi: str, symbol: str):
    """Latest day_close for one option contract (history + today), price + source."""
    sql = """
        SELECT a.day_close AS premium_option_price, a.date
        FROM (
            SELECT date, option_osi, symbol, day_close FROM "OptionDataMassiveHistory"
            WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, option_osi, symbol, day_close FROM "OptionDataMassive"
        ) AS a
        WHERE a.option_osi = :osi AND a.symbol = :symbol
          AND a.date <= CURRENT_DATE
        ORDER BY a.date DESC
        LIMIT 1
    """
    df = query_dataframe(sql, {"osi": option_osi, "symbol": symbol})
    if df is not None and not df.empty:
        d = df.iloc[0]["date"]
        return float(df.iloc[0]["premium_option_price"]), f"DB day_close ({d})"
    return None, "kein Preis in DB"


def _current_stock_price(symbol: str):
    """Latest close for a symbol (history + today), within the last week."""
    sql = """
        SELECT b.close, b.date
        FROM (
            SELECT * FROM "StockPricesYahooHistory" WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, * FROM "StockPricesYahoo"
        ) AS b
        WHERE b.symbol = :symbol
          AND b.date <= CURRENT_DATE
          AND b.date >= CURRENT_DATE - INTERVAL '1 week'
        ORDER BY b.date DESC
        LIMIT 1
    """
    df = query_dataframe(sql, {"symbol": symbol})
    if df is not None and not df.empty:
        return float(df.iloc[0]["close"])
    return None


# ---------------------------------------------------------------------------
# Tab 2 — Put-Roller (roll a sold cash-secured put down/out, 3-step traffic light)
# ---------------------------------------------------------------------------
@router.get("/roller/puts")
async def roller_open_puts(
    symbol: str = Query(..., min_length=1),
    entry_date: str = Query(..., description="Opening day of the put (YYYY-MM-DD)"),
    dte_min: int = Query(30, ge=1, le=400),
    dte_max: int = Query(60, ge=1, le=400),
    current_user: dict = Depends(get_current_user),
):
    """Load the puts that existed for a symbol on the entry date (roll_put_history.sql).

    Returns one row per (expiration_date, strike) with option_osi, strike_price,
    premium_option_price (day_close at entry), days_to_expiration, expiration_date,
    contract_type, open_interest, day_volume — i.e. the picker feed for choosing the
    put to roll.
    """
    params = {"symbol": symbol, "entry_date": entry_date,
              "dte_min": dte_min, "dte_max": dte_max}
    cached = cache.get("roller_puts", params)
    if cached is not None:
        return cached

    df = query_sql_file("roll_put_history.sql", params)
    result = df_to_json_safe(df) if df is not None and not df.empty else []
    cache.set("roller_puts", params, result, ttl=300)
    return result


@router.get("/roller/price")
async def roller_current_price(
    symbol: str = Query(..., min_length=1),
    option_osi: str = Query(..., description="OSI of the sold put"),
    current_user: dict = Depends(get_current_user),
):
    """Live-ish DB prices for the roller: current put day_close + current stock close.

    Returns {put_price, put_price_source, stock_price} (per-share values). Values are
    null when no DB price is available.
    """
    params = {"symbol": symbol, "option_osi": option_osi}
    cached = cache.get("roller_price", params)
    if cached is not None:
        return cached

    put_price, price_src = _current_put_price(option_osi, symbol)
    stock_price = _current_stock_price(symbol)
    result = {
        "put_price": put_price,
        "put_price_source": price_src,
        "stock_price": stock_price,
    }
    cache.set("roller_price", params, result, ttl=300)
    return result


@router.get("/roller/candidates")
async def roller_candidates(
    symbol: str = Query(..., min_length=1),
    K: float = Query(..., gt=0, description="Strike of the existing sold put"),
    S: float = Query(..., gt=0, description="Current stock price"),
    P_eroeffnung: float = Query(..., description="Opening premium, absolute $/contract (per-share * 100)"),
    P_heute: float = Query(..., description="Current put price to close, absolute $/contract"),
    n: int = Query(1, ge=1, description="Number of contracts of the existing position"),
    dte_rest: int = Query(0, ge=0, description="Days left on the EXISTING put (for Ludwig roll-trigger score)"),
    dte_min: int = Query(30, ge=1, le=400),
    dte_max: int = Query(60, ge=1, le=400),
    min_oi: int = Query(50, ge=0),
    min_vol: int = Query(10, ge=0),
    delta_min: float = Query(-1.0),
    delta_max: float = Query(-0.05),
    current_user: dict = Depends(get_current_user),
):
    """Roll candidates for a sold put, scored with the 3-step traffic-light logic.

    Loads roll_candidates.sql (liquid OTM puts, strike <= K) and evaluates each row
    under all three roll stages:
      - stufe 1 (Vertikal): lower strike, same #contracts (n)
      - stufe 2 (Horizontal): same strike (K2 == K), same #contracts (n)
      - stufe 3 (Verdoppeln): lower strike, doubled #contracts (2n)

    Returns:
      {
        position: {inner_value, time_value, breakeven_old, pnl_abs, pnl_pct, roll_trigger},
        stufe1|stufe2|stufe3: [ {strike_price, expiration_date, days_to_expiration,
              open_interest, day_volume, premium_share, netto_abs, netto_pro_aktie,
              breakeven_new, breakeven_old, kapital_noetig, ampel} ... ]
      }
    All monetary result fields are absolute $ (contract-level) except premium_share.
    """
    params = {
        "symbol": symbol, "K": K, "S": S, "P_eroeffnung": P_eroeffnung,
        "P_heute": P_heute, "n": n, "dte_rest": dte_rest,
        "dte_min": dte_min, "dte_max": dte_max,
        "min_oi": min_oi, "min_vol": min_vol,
        "delta_min": delta_min, "delta_max": delta_max,
    }
    cached = cache.get("roller_candidates", params)
    if cached is not None:
        return cached

    import pandas as pd
    from src.roll_support_calc import (
        position_status, roll_candidate, pnl_breakdown, roll_trigger_score,
    )

    pos = position_status(K=K, S=S, P_eroeffnung=P_eroeffnung, P_heute=P_heute, n=n)
    trigger = roll_trigger_score(P_heute=P_heute, P_eroeffnung=P_eroeffnung, dte=dte_rest)
    breakdown = pnl_breakdown(K=K, S=S, P_eroeffnung=P_eroeffnung, P_heute=P_heute, n=n)

    sql_params = {
        "symbol": symbol, "K": K,
        "dte_min": dte_min, "dte_max": dte_max,
        "min_oi": min_oi, "min_vol": min_vol,
        "delta_min": delta_min, "delta_max": delta_max,
    }
    df = query_sql_file("roll_candidates.sql", sql_params)

    def _eval(stage: int, contracts: int, only_same_strike: bool):
        out = []
        if df is None or df.empty:
            return out
        for _, o in df.iterrows():
            K2 = float(o["strike_price"])
            if only_same_strike and abs(K2 - K) > 1e-9:
                continue
            if not only_same_strike and abs(K2 - K) <= 1e-9:
                # stufe 1/3 target lower strikes; skip the equal-strike row
                continue
            P_neu = float(o["premium_option_price"]) * 100.0
            r = roll_candidate(stufe=stage, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                               P_heute=P_heute, P_neu=P_neu, n=contracts)
            out.append({
                "strike_price": K2,
                "expiration_date": str(o["expiration_date"]),
                "days_to_expiration": int(o["days_to_expiration"]),
                "open_interest": int(o["open_interest"]) if pd.notna(o["open_interest"]) else None,
                "day_volume": int(o["day_volume"]) if pd.notna(o["day_volume"]) else None,
                "premium_share": float(o["premium_option_price"]),
                "netto_abs": r["netto_abs"],
                "netto_pro_aktie": r["netto_pro_aktie"],
                "breakeven_new": r["breakeven_new"],
                "breakeven_old": r["breakeven_old"],
                "kapital_noetig": r["kapital_noetig"],
                "ampel": r["ampel"],
            })
        # traffic-light rank then highest net premium first (like master's UI)
        rank = {"✅": 0, "⚠️": 1, "❌": 2}
        out.sort(key=lambda c: (rank.get(c["ampel"], 3), -c["netto_abs"]))
        return out

    result = {
        "position": {
            "inner_value": pos["inner_value"],
            "time_value": pos["time_value"],
            "breakeven_old": pos["breakeven_old"],
            "pnl_abs": pos["pnl_abs"],
            "pnl_pct": pos["pnl_pct"],
            "im_gewinn": breakdown["im_gewinn"],
            "grund": breakdown["grund"],
            "pnl_lines": breakdown["lines"],
            "roll_trigger": trigger,
        },
        "stufe1": _eval(1, n, only_same_strike=False),
        "stufe2": _eval(2, n, only_same_strike=True),
        "stufe3": _eval(3, 2 * n, only_same_strike=False),
    }
    cache.set("roller_candidates", params, result, ttl=300)
    return result


class RollExplainRequest(BaseModel):
    """Inputs for a single roll-candidate plain-language breakdown."""
    stufe: int
    K: float
    K2: float
    P_eroeffnung: float
    P_heute: float
    P_neu: float  # absolute $/contract of the new put (per-share * 100)
    n: int


@router.post("/roller/explain")
async def roller_explain(
    request: RollExplainRequest,
    current_user: dict = Depends(get_current_user),
):
    """Plain-language derivation for one chosen roll candidate (roll_candidate_explained).

    Returns the full roll_candidate result (netto_abs, netto_pro_aktie, breakeven_new,
    breakeven_old, kapital_noetig, ampel, stufe) plus a `steps` list of
    {label, formel, wert} — mirrors master's "Details →" card.
    """
    from src.roll_support_calc import roll_candidate_explained
    exp = roll_candidate_explained(
        stufe=request.stufe, K=request.K, K2=request.K2,
        P_eroeffnung=request.P_eroeffnung, P_heute=request.P_heute,
        P_neu=request.P_neu, n=request.n,
    )
    return exp


# ---------------------------------------------------------------------------
# Tab 3 — Spread-Roller (roll a vertical spread, 4 spread types)
# ---------------------------------------------------------------------------
@router.get("/spread-roller/types")
async def spread_roller_types(current_user: dict = Depends(get_current_user)):
    """Return the SPREAD_TYPES catalog (bull_put / bear_call / bull_call / bear_put).

    Each entry: {key, contract, strategy, primary, second_dir, be_dir, label, opposite}.
    Used by the React page to render the spread-type picker and leg semantics.
    """
    from src.spread_roll_calc import SPREAD_TYPES
    return [{"key": k, **v} for k, v in SPREAD_TYPES.items()]


@router.get("/spread-roller/open")
async def spread_roller_open(
    symbol: str = Query(..., min_length=1),
    entry_date: str = Query(..., description="Opening day of the spread (YYYY-MM-DD)"),
    expiration_date: str = Query(..., description="Expiration of the existing spread (YYYY-MM-DD)"),
    current_user: dict = Depends(get_current_user),
):
    """Historical chain (put+call) of one expiration on the spread's opening day.

    Loads spread_open_history.sql — used to pre-fill the opening credit/debit of both
    legs from that day's day_close. Returns rows with contract_type, strike_price,
    premium_option_price, expiration_date, etc.
    """
    params = {"symbol": symbol, "entry_date": entry_date,
              "expiration_date": expiration_date}
    cached = cache.get("spread_open", params)
    if cached is not None:
        return cached

    df = query_sql_file("spread_open_history.sql", params)
    result = df_to_json_safe(df) if df is not None and not df.empty else []
    cache.set("spread_open", params, result, ttl=300)
    return result


@router.get("/spread-roller/chain")
async def spread_roller_chain(
    symbol: str = Query(..., min_length=1),
    expiration_date: str = Query(..., description="Expiration to load the current chain for"),
    current_user: dict = Depends(get_current_user),
):
    """Current full option chain (put+call) for one expiration (option_chain_symbol.sql).

    Used to pick the two spread legs and read today's last prices / live_stock_price.
    """
    params = {"symbol": symbol, "expiration_date": expiration_date}
    cached = cache.get("spread_chain", params)
    if cached is not None:
        return cached

    df = query_sql_file("option_chain_symbol.sql", params)
    result = df_to_json_safe(df) if df is not None and not df.empty else []
    cache.set("spread_chain", params, result, ttl=300)
    return result


@router.get("/spread-roller/candidates")
async def spread_roller_candidates(
    symbol: str = Query(..., min_length=1),
    short_strike: float = Query(..., gt=0, description="Short leg strike of the existing spread"),
    long_strike: float = Query(..., gt=0, description="Long leg strike of the existing spread"),
    width: float = Query(..., gt=0, description="Spread width in $/share (|short-long|)"),
    credit_open: float = Query(..., description="Opening credit (CREDIT) or paid debit (DEBIT), $/contract"),
    debit_now: float = Query(..., description="Current close debit (CREDIT) or value/credit (DEBIT), $/contract"),
    n: int = Query(1, ge=1, description="Number of spreads"),
    spread_type: str = Query("bull_put", description="bull_put | bear_call | bull_call | bear_put"),
    expiration_date: str = Query(..., description="Expiration of the existing spread (to split same/later)"),
    dte_min: int = Query(30, ge=1, le=400),
    dte_max: int = Query(60, ge=1, le=400),
    min_oi: int = Query(50, ge=0),
    min_vol: int = Query(10, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """Roll candidates for a vertical spread, grouped by named roll kind.

    Loads spread_roll_candidates.sql (fixed width, matching contract side/strategy) and
    evaluates each via spread_roll_candidate(). Candidates are grouped like master's tabs:
      - vertikal:   same expiration, different short strike, n contracts
      - horizontal: later expiration, same short strike, n contracts
      - diagonal:   later expiration, different short strike, n contracts
      - verdoppeln: same expiration, different short strike, 2n contracts

    Returns:
      {
        position: {gs_old, breakeven, max_loss_open, pnl_abs, pnl_pct, spread_type,
                   im_gewinn, grund, pnl_lines},
        <kind>: [ {short_strike, long_strike, expiration_date, dte, net_credit,
              netto_abs, netto_pro_aktie, gs_new, gs_old, max_loss, breakeven_new,
              added_debit_abs, risk_new, ampel} ... ]
      }
    """
    params = {
        "symbol": symbol, "short_strike": short_strike, "long_strike": long_strike,
        "width": width, "credit_open": credit_open, "debit_now": debit_now, "n": n,
        "spread_type": spread_type, "expiration_date": expiration_date,
        "dte_min": dte_min, "dte_max": dte_max, "min_oi": min_oi, "min_vol": min_vol,
    }
    cached = cache.get("spread_candidates", params)
    if cached is not None:
        return cached

    import pandas as pd
    from src.spread_roll_calc import (
        SPREAD_TYPES, spread_position_status, spread_pnl_breakdown, spread_roll_candidate,
    )

    meta = SPREAD_TYPES.get(spread_type, SPREAD_TYPES["bull_put"])

    pos = spread_position_status(
        short_strike=short_strike, width=width, credit_open=credit_open,
        debit_now=debit_now, n=n, spread_type=spread_type, long_strike=long_strike,
    )
    bd = spread_pnl_breakdown(
        short_strike=short_strike, width=width, credit_open=credit_open,
        debit_now=debit_now, n=n, spread_type=spread_type, long_strike=long_strike,
    )

    # symmetric ±2*width window around the old short strike (like master's default)
    strike_lo = short_strike - 2.0 * width
    strike_hi = short_strike + 2.0 * width
    sql_params = {
        "symbol": symbol,
        "contract_type": meta["contract"], "strategy_type": meta["strategy"],
        "spread_width": width,
        "dte_min": dte_min, "dte_max": dte_max,
        "min_oi": min_oi, "min_vol": min_vol,
        "strike_lo": strike_lo, "strike_hi": strike_hi,
    }
    df = query_sql_file("spread_roll_candidates.sql", sql_params)

    old_exp = str(expiration_date)

    def _eval(kind: str, contracts: int, same_exp: bool, diff_short: bool):
        out = []
        if df is None or df.empty:
            return out
        for _, o in df.iterrows():
            row_exp = str(o["expiration_date"])
            if same_exp and row_exp != old_exp:
                continue
            if not same_exp and not (row_exp > old_exp):
                continue
            sn = float(o["short_strike"])
            if diff_short and abs(sn - short_strike) <= 1e-9:
                continue
            if not diff_short and abs(sn - short_strike) > 1e-9:
                continue
            ln = float(o["long_strike"])
            credit_new = abs(float(o["net_credit"])) * 100.0
            r = spread_roll_candidate(
                stufe=0, roll_kind=kind, spread_type=spread_type,
                short_old=short_strike, short_new=sn,
                long_old=long_strike, long_new=ln,
                width=width, credit_open=credit_open, debit_close=debit_now,
                credit_new=credit_new, n=contracts,
            )
            out.append({
                "short_strike": sn,
                "long_strike": ln,
                "expiration_date": row_exp,
                "dte": int(o["dte"]) if pd.notna(o["dte"]) else None,
                "net_credit": float(o["net_credit"]),
                "short_oi": int(o["short_oi"]) if pd.notna(o.get("short_oi")) else None,
                "short_volume": int(o["short_volume"]) if pd.notna(o.get("short_volume")) else None,
                "netto_abs": r["netto_abs"],
                "netto_pro_aktie": r["netto_pro_aktie"],
                "gs_new": r["gs_new"],
                "gs_old": r["gs_old"],
                "max_loss": r["max_loss"],
                "breakeven_new": r["breakeven_new"],
                "added_debit_abs": r["added_debit_abs"],
                "risk_new": r["risk_new"],
                "ampel": r["ampel"],
            })
        out.sort(key=lambda c: (c["short_strike"] if c["short_strike"] is not None else 0), reverse=True)
        return out

    result = {
        "position": {
            "gs_old": pos["gs_old"],
            "breakeven": pos["breakeven"],
            "max_loss_open": pos["max_loss_open"],
            "pnl_abs": pos["pnl_abs"],
            "pnl_pct": pos["pnl_pct"],
            "spread_type": pos["spread_type"],
            "is_credit": meta["strategy"] == "credit",
            "im_gewinn": bd["im_gewinn"],
            "grund": bd["grund"],
            "pnl_lines": bd["lines"],
        },
        "vertikal": _eval("vertikal", n, same_exp=True, diff_short=True),
        "horizontal": _eval("horizontal", n, same_exp=False, diff_short=False),
        "diagonal": _eval("diagonal", n, same_exp=False, diff_short=True),
        "verdoppeln": _eval("verdoppeln", 2 * n, same_exp=True, diff_short=True),
    }
    cache.set("spread_candidates", params, result, ttl=300)
    return result


# ---------------------------------------------------------------------------
# Tab 4 — Put-Browser (browse all tradable puts across symbols)
# ---------------------------------------------------------------------------
@router.get("/browser/puts")
async def browser_puts(
    dte_min: int = Query(21, ge=1, le=400),
    dte_max: int = Query(45, ge=1, le=400),
    min_puffer_pct: float = Query(5.0, ge=0.0, le=90.0),
    min_ann_pct: float = Query(12.0, ge=0.0),
    price_min: float = Query(15.0, ge=0.0),
    price_max: float = Query(150.0, ge=0.0),
    min_oi: int = Query(100, ge=0),
    min_vol: int = Query(20, ge=0),
    min_premium_share: float = Query(0.10, ge=0.0),
    current_user: dict = Depends(get_current_user),
):
    """Browse all tradable puts (across symbols) with liquidity/buffer/annualized filters.

    Ports master's Put-Browser inline query over "OptionDataMerged" (no dedicated .sql
    file — option_chain_symbol.sql is single-symbol only). Buffer filter is applied in
    SQL (strike <= live_stock_price * (1 - puffer%)); the annualized filter is applied
    after. Capped at 500 rows, ordered by ann_pct DESC.

    Returns rows: symbol, strike_price, expiration_date, days_to_expiration,
    premium_option_price, open_interest, day_volume, greeks_delta, implied_volatility,
    iv_rank, live_stock_price, puffer_pct, rendite_pct, ann_pct.
    """
    params = {
        "dte_min": dte_min, "dte_max": dte_max, "min_puffer_pct": min_puffer_pct,
        "min_ann_pct": min_ann_pct, "price_min": price_min, "price_max": price_max,
        "min_oi": min_oi, "min_vol": min_vol, "min_premium_share": min_premium_share,
    }
    cached = cache.get("browser_puts", params)
    if cached is not None:
        return cached

    puffer_factor = 1.0 - min_puffer_pct / 100.0
    sql = """
        SELECT
            o.symbol,
            o.strike_price,
            o.expiration_date,
            o.days_to_expiration,
            o.premium_option_price,
            o.open_interest,
            o.day_volume,
            o.greeks_delta,
            o.implied_volatility,
            o.iv_rank,
            o.live_stock_price,
            ROUND(((o.live_stock_price - o.strike_price) / NULLIF(o.live_stock_price,0) * 100)::numeric, 1) AS puffer_pct,
            ROUND((o.premium_option_price / NULLIF(o.strike_price,0) * 100)::numeric, 2)                    AS rendite_pct,
            ROUND((o.premium_option_price / NULLIF(o.strike_price,0) * 365.0 / NULLIF(o.days_to_expiration,0) * 100)::numeric, 1) AS ann_pct
        FROM "OptionDataMerged" o
        WHERE o.contract_type = 'put'
          AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
          AND o.open_interest >= :min_oi
          AND o.day_volume >= :min_vol
          AND o.premium_option_price >= :min_premium_share
          AND o.live_stock_price BETWEEN :price_min AND :price_max
          AND o.strike_price <= o.live_stock_price * :puffer_factor
        ORDER BY ann_pct DESC NULLS LAST
        LIMIT 500
    """
    sql_params = {
        "dte_min": dte_min, "dte_max": dte_max,
        "min_oi": min_oi, "min_vol": min_vol,
        "min_premium_share": min_premium_share,
        "price_min": price_min, "price_max": price_max,
        "puffer_factor": puffer_factor,
    }
    df = query_dataframe(sql, sql_params)
    if df is not None and not df.empty and min_ann_pct > 0:
        df = df[df["ann_pct"] >= min_ann_pct]

    result = df_to_json_safe(df) if df is not None and not df.empty else []
    cache.set("browser_puts", params, result, ttl=300)
    return result
