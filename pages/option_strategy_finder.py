"""Option Strategy Finder — Symbol oder Sektor -> Optionsstrategien im DTE-Fenster."""

import pandas as pd
import streamlit as st
from src.ui_strategy_display import display_strategy_details
from src.options_utils import OptionLeg, StrategyMetrics, calculate_apdi
from src.page_display_dataframe import create_claude_prompt_strategy_finder

from config import PATH_DATABASE_QUERY_FOLDER, RISK_FREE_RATE
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.streamlit_helpers import render_date_filter
from src.black_scholes import PutValue, CallValue

# ── Delta-Konstanten (Defaults, werden per Slider überschrieben) ──────────────
_DELTA_SHORT_DEFAULT    = 0.30
_DELTA_SPREAD_BUY_DEF   = 0.15
MIN_OI_DEFAULT          = 50
MIN_VOL_DEFAULT         = 5

# ── "Langweilige Aktien" Kriterien (wie Spreads Enhanced) ─────────────────────
BORING_SECTORS = {
    "Consumer Defensive", "Utilities", "Healthcare",
    "Consumer Staples", "Communication Services",
}
BORING_MAX_BETA = 1.0
BORING_MAX_IV = 0.40
BORING_MIN_MARKET_CAP = 20_000_000_000  # $20 Mrd

# ── Strategie → Score-Richtung (mit User geklärt) ─────────────────────────────
_STRATEGY_DIRECTION = {
    "Short Put":        "bull",
    "Bull Put Spread":  "bull",
    "Bear Call Spread": "bear",
    "Covered Call":     "bear",
    "Iron Condor":      None,   # neutral → kein Score
}


def _is_num(v) -> bool:
    return v is not None and not (isinstance(v, float) and v != v)


def _tech_score(tech: dict, direction: str, style: str) -> int | None:
    """
    Technischer Timing-Score (0-6), richtungs- + stil-abhängig.
    Bildet die Kriterien aus spreads_enhanced_multidate_input.sql exakt 1:1 ab.
    direction: 'bull' | 'bear' ; style: 'trend' | 'dip'. None wenn Indikatoren fehlen.
    """
    if direction is None:
        return None
    close = tech.get("close")
    ema50 = tech.get("EMA_50")
    ema200 = tech.get("EMA_200")
    rsi = tech.get("RSI_14")
    stoch_k = tech.get("STOCHk_14_3_1")
    stoch_h = tech.get("STOCHh_14_3_1")
    macdh = tech.get("MACDh_12_26_9")
    adx = tech.get("ADX_10")
    dmp = tech.get("DMP_10")
    dmn = tech.get("DMN_10")
    needed = [close, ema50, ema200, rsi, stoch_k, adx, dmp, dmn, macdh]
    if not all(_is_num(v) for v in needed):
        return None

    if direction == "bull" and style == "trend":
        s = [close > ema200, close > ema50, 45 <= rsi <= 70,
             20 <= stoch_k <= 80, adx > 18 and dmp > dmn, macdh > 0]
    elif direction == "bull" and style == "dip":
        if not _is_num(stoch_h):
            return None
        s = [close > ema200, 30 <= rsi <= 45, stoch_k < 20,
             stoch_h > 0, adx > 18 and dmp > dmn, macdh > 0]
    elif direction == "bear" and style == "trend":
        s = [close < ema200, close < ema50, 30 <= rsi <= 55,
             20 <= stoch_k <= 80, adx > 18 and dmn > dmp, macdh < 0]
    else:  # bear + dip
        if not _is_num(stoch_h):
            return None
        s = [close < ema200, 55 <= rsi <= 70, stoch_k > 80,
             stoch_h < 0, adx > 18 and dmn > dmp, macdh < 0]
    return int(sum(bool(x) for x in s))


# ── Datenladen ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def _load_sectors() -> list[str]:
    df = select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "get_sectors.sql",
    )
    if df is None or df.empty:
        return []
    return sorted(df.iloc[:, 0].dropna().astype(str).tolist())


@st.cache_data(ttl=600)
def _load_symbols_for_sector(sector: str, min_market_cap_b: float = 0.0) -> list[str]:
    query = """
        SELECT DISTINCT o.symbol
        FROM "OptionDataMerged" o
        JOIN "FundamentalData" f ON f.symbol = o.symbol
        WHERE f.company_sector = :sector
    """
    if min_market_cap_b > 0:
        query += ' AND o."Summary_marketCap" >= :min_mcap'
    query += " ORDER BY o.symbol ASC"
    params = {"sector": sector}
    if min_market_cap_b > 0:
        params["min_mcap"] = min_market_cap_b * 1_000_000_000
    df = select_into_dataframe(query=query, params=params)
    if df is None or df.empty:
        return []
    return df["symbol"].dropna().astype(str).tolist()


@st.cache_data(ttl=600)
def _load_all_symbols(min_market_cap_b: float = 0.0) -> list[str]:
    query = 'SELECT DISTINCT symbol FROM "OptionDataMerged" WHERE 1=1'
    params = {}
    if min_market_cap_b > 0:
        query += ' AND "Summary_marketCap" >= :min_mcap'
        params["min_mcap"] = min_market_cap_b * 1_000_000_000
    query += " ORDER BY symbol ASC"
    df = select_into_dataframe(query=query, params=params)
    if df is None or df.empty:
        return []
    return df["symbol"].dropna().astype(str).tolist()


@st.cache_data(ttl=1800)
def _load_chain(date: str, symbol: str, dte_min: int, dte_max: int,
                min_oi: int, min_vol: int) -> pd.DataFrame:
    df = select_timetravel_into_dataframe(
        date=date,
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "strategy_finder_chain.sql",
        params={
            "symbol": symbol.upper().strip(),
            "dte_min": dte_min,
            "dte_max": dte_max,
            "min_open_interest": min_oi,
            "min_day_volume": min_vol,
        },
    )
    if df is None or df.empty:
        return pd.DataFrame()
    for col in ["strike_price", "premium", "greeks_delta", "implied_volatility",
                "greeks_theta", "open_interest", "day_volume", "stock_price",
                "iv_rank", "hv_30d", "market_cap",
                "RSI_14", "STOCHk_14_3_1", "STOCHh_14_3_1", "EMA_50", "EMA_200",
                "MACDh_12_26_9", "ADX_10", "DMP_10", "DMN_10", "beta"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["dte"] = pd.to_numeric(df["dte"], errors="coerce")
    return df


# ── Strategie-Builder ─────────────────────────────────────────────────────────

def _closest_delta(sub: pd.DataFrame, target: float, max_delta: float | None = None) -> pd.Series | None:
    if sub.empty:
        return None
    sub = sub.copy()
    if max_delta is not None:
        sub = sub[sub["greeks_delta"].abs() <= max_delta]
        if sub.empty:
            return None
    sub["_dd"] = (sub["greeks_delta"].abs() - target).abs()
    return sub.loc[sub["_dd"].idxmin()]


def _bs(S, K, iv, dte, is_call) -> float | None:
    try:
        if any(v is None or (isinstance(v, float) and (v != v)) for v in [S, K, iv, dte]):
            return None
        if iv <= 0 or dte <= 0:
            return None
        fn = CallValue if is_call else PutValue
        return round(fn(float(S), float(K), float(iv), float(dte), RISK_FREE_RATE), 2)
    except Exception:
        return None


def _leg(row: pd.Series, is_call: bool, is_long: bool, stock_price: float) -> dict:
    K   = float(row["strike_price"])
    prem = float(row["premium"])
    iv   = float(row["implied_volatility"])
    dte  = float(row["dte"])
    bs   = _bs(stock_price, K, iv, dte, is_call)
    return {
        "type":    "Call" if is_call else "Put",
        "action":  "Long" if is_long else "Short",
        "strike":  K,
        "premium": prem,
        "bs":      bs,
        "delta":   float(row["greeks_delta"]),
        "iv":      iv,
        "theta":   float(row.get("greeks_theta") or 0),
        "oi":      int(row.get("open_interest") or 0),
        "volume":  int(row.get("day_volume") or 0),
    }



def _earnings_before_expiry(s: dict) -> str | None:
    ed = s.get("earnings_date")
    if ed is None or pd.isna(ed):
        return None
    try:
        exp = pd.to_datetime(s["expiration"]).date()
        ear = pd.to_datetime(ed).date()
        if ear <= exp:
            return str(ear)
    except Exception:
        pass
    return None


def build_strategies(df: pd.DataFrame, min_profit: float, max_risk: float,
                     outlook: str, delta_short: float, delta_buy: float,
                     max_delta: float | None = None, score_style: str = "trend") -> list[dict]:
    if df.empty:
        return []

    stock_price = df["stock_price"].iloc[0]
    symbol = df["symbol"].iloc[0] if "symbol" in df.columns else ""
    company_name = df["company_name"].iloc[0] if "company_name" in df.columns else symbol
    company_sector = df["company_sector"].iloc[0] if "company_sector" in df.columns else None
    results: list[dict] = []

    # Tech-Indikatoren + Beta/MCap sind auf Underlying-Ebene (pro Symbol identisch) → erste Zeile.
    def _first(col):
        return df[col].iloc[0] if col in df.columns and len(df) else None
    tech = {
        "close": float(stock_price) if _is_num(stock_price) else None,
        "EMA_50": _first("EMA_50"), "EMA_200": _first("EMA_200"),
        "RSI_14": _first("RSI_14"), "STOCHk_14_3_1": _first("STOCHk_14_3_1"),
        "STOCHh_14_3_1": _first("STOCHh_14_3_1"), "MACDh_12_26_9": _first("MACDh_12_26_9"),
        "ADX_10": _first("ADX_10"), "DMP_10": _first("DMP_10"), "DMN_10": _first("DMN_10"),
    }
    sym_beta = _first("beta")
    sym_mcap = _first("market_cap")

    puts  = df[df["option_type"] == "put"].copy()
    calls = df[df["option_type"] == "call"].copy()

    for exp_date, exp_puts in puts.groupby("expiration_date"):
        dte = int(exp_puts["dte"].iloc[0])
        exp_calls = calls[calls["expiration_date"] == exp_date]

        # Short Put
        if outlook in ("Bullish", "Neutral"):
            leg = _closest_delta(exp_puts, delta_short, max_delta=max_delta)
            if leg is not None:
                credit = float(leg["premium"]) * 100
                risk   = float(leg["strike_price"]) * 100
                if credit >= min_profit and risk <= max_risk:
                    results.append(_row(
                        "Short Put", symbol, exp_date, dte,
                        f"Sell {leg['strike_price']:.2f}P",
                        credit, credit, risk,
                        float(leg["strike_price"]) - float(leg["premium"]),
                        credit / risk * 100,
                        float(leg["greeks_delta"]),
                        float(leg["implied_volatility"]),
                        float(leg.get("iv_rank") or 0),
                        (stock_price - float(leg["strike_price"])) / stock_price * 100,
                        leg.get("earnings_date"),
                        company_name=company_name,
                        company_sector=company_sector,
                        leg_data=[_leg(leg, is_call=False, is_long=False, stock_price=stock_price)],
                    ))

        # Covered Call
        if outlook in ("Neutral", "Bearish") and not exp_calls.empty:
            leg = _closest_delta(exp_calls, delta_short, max_delta=max_delta)
            if leg is not None:
                credit = float(leg["premium"]) * 100
                if credit >= min_profit:
                    results.append(_row(
                        "Covered Call", symbol, exp_date, dte,
                        f"Sell {leg['strike_price']:.2f}C",
                        credit,
                        credit + (float(leg["strike_price"]) - stock_price) * 100,
                        stock_price * 100,
                        stock_price - float(leg["premium"]),
                        credit / (stock_price * 100) * 100,
                        float(leg["greeks_delta"]),
                        float(leg["implied_volatility"]),
                        float(leg.get("iv_rank") or 0),
                        (float(leg["strike_price"]) - stock_price) / stock_price * 100,
                        leg.get("earnings_date"),
                        company_name=company_name,
                        company_sector=company_sector,
                        leg_data=[_leg(leg, is_call=True, is_long=False, stock_price=stock_price)],
                    ))

        # Bull Put Spread
        if outlook in ("Bullish", "Neutral") and len(exp_puts) >= 2:
            sell_leg = _closest_delta(exp_puts, delta_short, max_delta=max_delta)
            if sell_leg is not None:
                buy_cands = exp_puts[exp_puts["strike_price"] < sell_leg["strike_price"]]
                buy_leg = _closest_delta(buy_cands, delta_buy)
                if buy_leg is not None:
                    width  = float(sell_leg["strike_price"]) - float(buy_leg["strike_price"])
                    credit = (float(sell_leg["premium"]) - float(buy_leg["premium"])) * 100
                    risk   = width * 100 - credit
                    if credit >= min_profit and risk <= max_risk and credit > 0:
                        results.append(_row(
                            "Bull Put Spread", symbol, exp_date, dte,
                            f"Sell {sell_leg['strike_price']:.2f}P / Buy {buy_leg['strike_price']:.2f}P",
                            credit, credit, risk,
                            float(sell_leg["strike_price"]) - credit / 100,
                            credit / risk * 100 if risk > 0 else 0,
                            float(sell_leg["greeks_delta"]),
                            float(sell_leg["implied_volatility"]),
                            float(sell_leg.get("iv_rank") or 0),
                            (stock_price - float(sell_leg["strike_price"])) / stock_price * 100,
                            sell_leg.get("earnings_date"),
                            company_name=company_name,
                            company_sector=company_sector,
                        leg_data=[
                                _leg(sell_leg, is_call=False, is_long=False, stock_price=stock_price),
                                _leg(buy_leg,  is_call=False, is_long=True,  stock_price=stock_price),
                            ],
                        ))

        # Bear Call Spread
        if outlook in ("Bearish", "Neutral") and len(exp_calls) >= 2:
            sell_leg = _closest_delta(exp_calls, delta_short, max_delta=max_delta)
            if sell_leg is not None:
                buy_cands = exp_calls[exp_calls["strike_price"] > sell_leg["strike_price"]]
                buy_leg = _closest_delta(buy_cands, delta_buy)
                if buy_leg is not None:
                    width  = float(buy_leg["strike_price"]) - float(sell_leg["strike_price"])
                    credit = (float(sell_leg["premium"]) - float(buy_leg["premium"])) * 100
                    risk   = width * 100 - credit
                    if credit >= min_profit and risk <= max_risk and credit > 0:
                        results.append(_row(
                            "Bear Call Spread", symbol, exp_date, dte,
                            f"Sell {sell_leg['strike_price']:.2f}C / Buy {buy_leg['strike_price']:.2f}C",
                            credit, credit, risk,
                            float(sell_leg["strike_price"]) + credit / 100,
                            credit / risk * 100 if risk > 0 else 0,
                            float(sell_leg["greeks_delta"]),
                            float(sell_leg["implied_volatility"]),
                            float(sell_leg.get("iv_rank") or 0),
                            (float(sell_leg["strike_price"]) - stock_price) / stock_price * 100,
                            sell_leg.get("earnings_date"),
                            company_name=company_name,
                            company_sector=company_sector,
                        leg_data=[
                                _leg(sell_leg, is_call=True, is_long=False, stock_price=stock_price),
                                _leg(buy_leg,  is_call=True, is_long=True,  stock_price=stock_price),
                            ],
                        ))

        # Iron Condor
        if outlook == "Neutral" and len(exp_puts) >= 2 and len(exp_calls) >= 2:
            put_sell  = _closest_delta(exp_puts,  delta_short, max_delta=max_delta)
            call_sell = _closest_delta(exp_calls, delta_short, max_delta=max_delta)
            if put_sell is not None and call_sell is not None:
                put_buys  = exp_puts[exp_puts["strike_price"] < put_sell["strike_price"]]
                call_buys = exp_calls[exp_calls["strike_price"] > call_sell["strike_price"]]
                put_buy   = _closest_delta(put_buys,  delta_buy)
                call_buy  = _closest_delta(call_buys, delta_buy)
                if put_buy is not None and call_buy is not None:
                    pw = float(put_sell["strike_price"]) - float(put_buy["strike_price"])
                    cw = float(call_buy["strike_price"]) - float(call_sell["strike_price"])
                    pc = (float(put_sell["premium"]) - float(put_buy["premium"])) * 100
                    cc = (float(call_sell["premium"]) - float(call_buy["premium"])) * 100
                    total_credit = pc + cc
                    max_risk_ic  = max(pw, cw) * 100 - total_credit
                    if total_credit >= min_profit and max_risk_ic <= max_risk and total_credit > 0:
                        results.append(_row(
                            "Iron Condor", symbol, exp_date, dte,
                            (f"Sell {put_sell['strike_price']:.2f}P / Buy {put_buy['strike_price']:.2f}P  |  "
                             f"Sell {call_sell['strike_price']:.2f}C / Buy {call_buy['strike_price']:.2f}C"),
                            total_credit, total_credit, max_risk_ic,
                            float(put_sell["strike_price"]) - total_credit / 100,
                            total_credit / max_risk_ic * 100 if max_risk_ic > 0 else 0,
                            float(put_sell["greeks_delta"]),
                            float(put_sell["implied_volatility"]),
                            float(put_sell.get("iv_rank") or 0),
                            (stock_price - float(put_sell["strike_price"])) / stock_price * 100,
                            put_sell.get("earnings_date"),
                            company_name=company_name,
                            company_sector=company_sector,
                        leg_data=[
                                _leg(put_sell,  is_call=False, is_long=False, stock_price=stock_price),
                                _leg(put_buy,   is_call=False, is_long=True,  stock_price=stock_price),
                                _leg(call_sell, is_call=True,  is_long=False, stock_price=stock_price),
                                _leg(call_buy,  is_call=True,  is_long=True,  stock_price=stock_price),
                            ],
                        ))

    # stock_price + Tech/Beta/MCap in alle rows eintragen
    for r in results:
        r["_stock_price"] = float(stock_price)
        r["_tech"] = tech
        r["_beta"] = float(sym_beta) if _is_num(sym_beta) else None
        r["_market_cap"] = float(sym_mcap) if _is_num(sym_mcap) else None
        direction = _STRATEGY_DIRECTION.get(r["Strategie"])
        r["_score_direction"] = direction
        r["tech_score"] = _tech_score(tech, direction, score_style)
        r["_rsi"] = tech.get("RSI_14")
        r["_stoch_k"] = tech.get("STOCHk_14_3_1")
    return results


def _row(strat, symbol, exp_date, dte, legs, kredit, max_profit, max_risk,
         breakeven, ror, delta, iv, iv_rank, otm_pct, earnings_date,
         leg_data=None, company_name=None, company_sector=None) -> dict:
    return {
        "Strategie":   strat,
        "Symbol":      symbol,
        "Verfall":     exp_date,
        "DTE":         dte,
        "Beine":       legs,
        "Kredit $":    round(kredit, 0),
        "Max Profit $": round(max_profit, 0),
        "Max Risiko $": round(max_risk, 0),
        "RoR %":       round(ror, 1),
        "Breakeven":   round(breakeven, 2),
        "Delta":       round(delta, 2),
        "IV %":        round(iv * 100, 1),
        "IV Rank":     round(iv_rank, 0),
        "OTM %":       round(otm_pct, 1),
        "earnings_date": earnings_date,
        "_earnings_warn": bool(_earnings_before_expiry({
            "earnings_date": earnings_date, "expiration": exp_date
        })),
        "_legs": leg_data or [],
        "_stock_price": None,
        "_company_name": company_name,
        "_company_sector": company_sector,
        "_all_overpriced": all(
            (l.get("bs") is not None and l["premium"] > l["bs"])
            for l in (leg_data or [])
        ) if leg_data else False,
    }


# ── Tabellen-Rendering ────────────────────────────────────────────────────────

_DISPLAY_COLS = [
    "Strategie", "Symbol", "Verfall", "DTE", "Beine",
    "Kredit $", "Max Profit $", "Max Risiko $", "RoR %",
    "Breakeven", "Delta", "IV %", "IV Rank", "OTM %", "Score",
]


def _style_table(df: pd.DataFrame):
    def _ror(col):
        out = []
        for v in col:
            if v >= 15:
                out.append("color:#34d399;font-weight:700")
            elif v >= 8:
                out.append("color:#f59e0b;font-weight:700")
            else:
                out.append("color:#ef4444")
        return out

    def _ivr(col):
        out = []
        for v in col:
            if 35 <= v <= 65:
                out.append("color:#34d399;font-weight:700")
            elif 20 <= v <= 80:
                out.append("color:#f59e0b")
            else:
                out.append("color:#ef4444")
        return out

    return (
        df.style
        .apply(_ror, subset=["RoR %"])
        .apply(_ivr, subset=["IV Rank"])
        .format({
            "Kredit $":     "{:.0f}",
            "Max Profit $": "{:.0f}",
            "Max Risiko $": "{:.0f}",
            "RoR %":        "{:.1f}",
            "Breakeven":    "{:.2f}",
            "Delta":        "{:.2f}",
            "IV %":         "{:.1f}",
            "IV Rank":      "{:.0f}",
            "OTM %":        "{:.1f}",
        })
    )


def _render_detail(s: dict):
    """Detail-View für eine angeklickte Strategie-Zeile."""
    st.divider()

    # Header
    ror = s["RoR %"]
    ror_color = "#34d399" if ror >= 15 else ("#f59e0b" if ror >= 8 else "#ef4444")
    ivr = s["IV Rank"]
    ivr_color = "#34d399" if 35 <= ivr <= 65 else ("#f59e0b" if 20 <= ivr <= 80 else "#ef4444")
    stock_price = s.get("_stock_price") or 0.0

    st.markdown(
        f"<div style='display:flex;align-items:center;gap:16px;margin-bottom:8px;'>"
        f"<span style='font-size:22px;font-weight:700;'>{s['Strategie']} — {s['Symbol']}</span>"
        f"<span style='background:{ror_color}22;border:1px solid {ror_color}66;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;font-weight:700;color:{ror_color};'>RoR {ror:.1f}%</span>"
        f"<span style='background:{ivr_color}22;border:1px solid {ivr_color}66;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;font-weight:600;color:{ivr_color};'>IV Rank {ivr:.0f}</span>"
        f"{'<span style=\"background:#1e293b;border:1px solid #334155;border-radius:20px;padding:3px 14px;font-size:13px;color:#94a3b8;\">Kurs $' + f'{stock_price:.2f}' + '</span>' if stock_price else ''}"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Verfall: **{s['Verfall']}** · {s['DTE']} DTE")
    st.code(s["Beine"], language=None)

    if s["_earnings_warn"]:
        st.warning(f"Earnings vor Verfall ({s['earnings_date']}) — erhöhtes Gap-Risiko.")

    # Legs als OptionLeg-Objekte aufbauen
    raw_legs = s.get("_legs", [])
    option_legs = [
        OptionLeg(
            strike=l["strike"],
            premium=l["premium"],
            is_call=l["type"] == "Call",
            is_long=l["action"] == "Long",
            delta=l["delta"],
            iv=l["iv"],
            theta=l["theta"],
            oi=l["oi"],
            volume=l["volume"],
            bs_price=l["bs"],
        )
        for l in raw_legs
    ]

    # StrategyMetrics berechnen
    kredit   = s["Kredit $"]
    max_prof = s["Max Profit $"]
    max_risk = s["Max Risiko $"]
    dte      = s["DTE"]
    total_theta = sum(
        (l["theta"] if l["action"] == "Short" else -l["theta"])
        for l in raw_legs if l["theta"]
    )
    bpr = max_risk  # Buying Power Requirement = Max Risiko bei Credit Spreads
    apdi = calculate_apdi(max_prof, dte, bpr)

    metrics = StrategyMetrics(
        max_profit=max_prof,
        max_loss=max_risk,
        bpr=bpr,
        expected_value=0.0,   # kein Monte Carlo hier
        total_theta=total_theta,
        profit_to_bpr=max_prof / bpr * 100 if bpr > 0 else 0,
        apdi=apdi,
        apdi_ev=0.0,
        iv_correction_factor=1.0,
        corrected_volatility=s["IV %"] / 100,
    )

    # Short-Strike der Strategie (für Sicherheitspuffer). Bei Iron Condor: Short-Put-Strike.
    short_legs = [l for l in raw_legs if l["action"] == "Short"]
    direction = s.get("_score_direction")  # bull | bear | None
    # Puffer-Richtung: Put-Seite (Bull Put/Short Put/IC) misst nach unten, Call-Seite nach oben.
    is_put = direction != "bear"  # bull + neutral(IC) => Put-Referenz nach unten
    if direction == "bear":
        ref_short = next((l for l in short_legs if l["type"] == "Call"), None)
    else:
        ref_short = next((l for l in short_legs if l["type"] == "Put"),
                         short_legs[0] if short_legs else None)
    sell_strike = ref_short["strike"] if ref_short else None

    extra_info = {
        "iv_rank":        s["IV Rank"],
        "iv_percentile":  None,
        "company_sector": s.get("_company_sector"),
        "company_industry": None,
        "analyst_mean_target": None,
        "close": stock_price,
        # Sicherheitspuffer
        "sell_strike": sell_strike,
        "break_even": s.get("Breakeven"),
        "is_put": is_put,
        # Technische Signale (richtungs-/stil-abhängig). Bei Iron Condor (direction None)
        # keine Tech-Signale, da neutral.
        "tech_indicators": s.get("_tech") if direction else None,
        "tech_score_direction": direction if direction else "bull",
        "tech_score_style": st.session_state.get("sf_score_style", "trend"),
    }

    display_strategy_details(s["Symbol"], s.get("_company_name") or s["Symbol"], option_legs, metrics, extra_info)

    claude_url = create_claude_prompt_strategy_finder(s, sector=s.get("_company_sector"))
    st.link_button("Claude AI Analyse", claude_url, type="primary", use_container_width=True)


def _render_table(rows: list[dict], tab_key: str):
    if not rows:
        st.info("Keine Treffer in dieser Kategorie.")
        return
    rows = [dict(r) for r in rows]  # nicht die Originale mutieren
    for r in rows:
        ts = r.get("tech_score")
        r["Score"] = f"{int(ts)}/6" if _is_num(ts) else "–"
    df = pd.DataFrame(rows)[_DISPLAY_COLS].copy()
    warns = [r for r in rows if r["_earnings_warn"]]
    if warns:
        syms = ", ".join(sorted({r["Symbol"] for r in warns}))
        st.warning(f"Earnings vor Verfall: {syms} — erhöhtes Gap-Risiko prüfen.")

    event = st.dataframe(
        _style_table(df),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"sf_table_{tab_key}",
        column_config={
            "Beine": st.column_config.TextColumn("Beine", width="large"),
            "Kredit $":     st.column_config.NumberColumn("Kredit $",     format="$%.0f"),
            "Max Profit $": st.column_config.NumberColumn("Max Profit $", format="$%.0f"),
            "Max Risiko $": st.column_config.NumberColumn("Max Risiko $", format="$%.0f"),
            "Breakeven":    st.column_config.NumberColumn("Breakeven",    format="$%.2f"),
            "Score": st.column_config.TextColumn("Score", help="Techn. Timing-Score 0-6 passend zur Strategie-Richtung; – = neutral/keine Daten"),
        },
    )

    sel_rows = event.selection.rows if hasattr(event, "selection") else []
    if sel_rows:
        _render_detail(rows[sel_rows[0]])
    else:
        st.caption("Zeile anklicken für Details.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("Option Strategy Finder")
    st.caption("Symbol oder Sektor eingeben — alle passenden Strategien im gewählten DTE-Fenster.")

    selected_date = render_date_filter(
        date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
    )

    # ── Symbolauswahl ─────────────────────────────────────────────────────────
    sel_mode = st.radio(
        "Symbolauswahl",
        ["Einzelnes Symbol", "Aus Sektor"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if sel_mode == "Einzelnes Symbol":
        symbol_input = st.text_input(
            "Symbol", value=st.session_state.get("sf_last_symbol", ""),
            placeholder="z.B. AAPL, MSFT, SPY",
        ).upper().strip()
        symbols_to_scan = [symbol_input] if symbol_input else []
        min_market_cap_b = 0.0
    else:
        min_market_cap_b = st.slider(
            "Min. Market Cap (Mrd $)", 0.0, 50.0, 2.0, 0.5,
            help="Symbole unter diesem Marktwert werden nicht geladen. Default: 2 Mrd."
        )
        sectors = _load_sectors()
        chosen_sector = st.selectbox(
            "Sektor", [""] + sectors,
            index=0,
            placeholder="Sektor wählen...",
        )
        if chosen_sector:
            sector_symbols = _load_symbols_for_sector(chosen_sector, min_market_cap_b=min_market_cap_b)
            chosen_symbols = st.multiselect(
                f"Symbole aus {chosen_sector} ({len(sector_symbols)} verfügbar)",
                sector_symbols,
                default=[],
                placeholder="Alle oder gezielt auswählen...",
            )
            symbols_to_scan = chosen_symbols if chosen_symbols else sector_symbols
        else:
            symbols_to_scan = []

    # ── Parameter ─────────────────────────────────────────────────────────────
    with st.expander("Parameter", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            outlook    = st.radio("Marktmeinung", ["Bullish", "Neutral", "Bearish"], index=1, horizontal=True)
            dte_range  = st.slider("DTE-Fenster", 0, 120, (21, 60))
        with c2:
            delta_short = st.slider("Delta Sell-Leg", 0.05, 0.50, _DELTA_SHORT_DEFAULT, 0.05,
                                    help="Ziel-Delta für den verkauften Strike (Short Put, Short Call, Spread-Sell-Bein).")
            delta_buy   = st.slider("Delta Buy-Leg (Spreads)", 0.05, 0.40, _DELTA_SPREAD_BUY_DEF, 0.05,
                                    help="Ziel-Delta für den gekauften Strike bei Bull Put / Bear Call / IC.")
            use_max_delta = st.toggle("Max Delta erzwingen", value=False,
                                      help="Sell-Leg Delta darf diesen Wert nicht überschreiten. "
                                           "Strikes mit |Delta| > Max werden ignoriert.")
            max_delta_val = st.slider("Max Delta (Sell-Leg)", 0.05, 0.80, delta_short + 0.10, 0.05,
                                      disabled=not use_max_delta,
                                      help="Absoluter Delta-Grenzwert. Alles darüber wird verworfen.")
            strategies  = st.multiselect(
                "Strategien",
                ["Short Put", "Covered Call", "Bull Put Spread", "Bear Call Spread", "Iron Condor"],
                default=["Short Put", "Bull Put Spread", "Iron Condor"],
            )
        with c3:
            min_profit = st.number_input("Min. Kredit ($)", 0, 10000, 50, 10)
            max_risk   = st.number_input("Max. Risiko ($)", 100, 500000, 2000, 100)
            min_oi     = st.number_input("Min. Open Interest", 0, 10000, MIN_OI_DEFAULT, 10)
            min_vol    = st.number_input("Min. Tagesvolumen", 0, 10000, MIN_VOL_DEFAULT, 1)
            min_puffer = st.slider("Min. Puffer % (OTM)", 0, 30, 0, 1,
                                   help="Sell-Strike muss mindestens X% vom aktuellen Kurs entfernt sein.")
            exclude_earnings = st.toggle("Earnings ausschließen", value=False,
                                         help="Alle Strategien ausblenden, bei denen Earnings vor dem Verfall liegen.")
            only_overpriced = st.toggle("Nur BS-überbewertet", value=False,
                                        help="Nur Strategien zeigen, bei denen ALLE Legs teurer als der BS-Preis sind (gut für Prämienverkäufer).")

    # ── Technische Filter (wie Spreads Enhanced) ──────────────────────────────
    with st.expander("Technische Filter", expanded=False):
        tc1, tc2, tc3 = st.columns(3)
        with tc1:
            score_style = st.radio(
                "Score-Stil", ["trend", "dip"],
                format_func=lambda k: "Trend/Stärke" if k == "trend" else "Dip/Rücksetzer",
                horizontal=True,
                key="sf_score_style",
                help="Trend/Stärke: stabil im Trend, nicht überverkauft (kein fallendes Messer). "
                     "Dip/Rücksetzer: in überverkaufte Schwäche verkaufen. Score-Richtung folgt "
                     "der Strategie (Short/Bull Put=bull, Bear Call/Covered Call=bear, Iron Condor=neutral).",
            )
            min_tech_score = st.slider("Min Tech-Score (0=aus)", 0, 6, 0,
                                       help="Filtert nach erfüllten technischen Timing-Kriterien (0-6) "
                                            "passend zur Richtung der jeweiligen Strategie. Iron Condor "
                                            "(neutral) wird vom Score-Filter nicht betroffen.")
        with tc2:
            rsi_range = st.slider("RSI 14 Bereich", 0, 100, (0, 100),
                                  help="Zeigt nur Symbole mit RSI in diesem Bereich. 0–100 = aus. "
                                       "Für 'nicht überverkauft' z.B. 40–70.")
            stoch_range = st.slider("Stochastik %K Bereich", 0, 100, (0, 100),
                                    help="Zeigt nur Symbole mit Stochastik %K in diesem Bereich. "
                                         "0–100 = aus. Für 'nicht über-/unterkauft' z.B. 20–80.")
        with tc3:
            boring_only = st.toggle("Nur langweilige Aktien", value=False,
                                    help="Nur stabile Large-Caps (Coca-Cola/Pepsi-Typ): Beta ≤ 1.0, "
                                         "IV ≤ 40%, Market Cap ≥ $20 Mrd, defensive Sektoren. "
                                         "Für ruhige, planbare Prämie.")

    run = st.button("Strategien suchen", type="primary", use_container_width=True)

    if not run and "sf_results" not in st.session_state:
        st.info("Symbol wählen und auf Strategien suchen klicken.")
        return

    if run:
        if not symbols_to_scan:
            st.error("Kein Symbol gewählt.")
            return
        # Scan
        all_results: list[dict] = []
        progress = st.progress(0, text=f"Lade Daten... (0/{len(symbols_to_scan)})")
        for i, sym in enumerate(symbols_to_scan):
            progress.progress((i + 1) / len(symbols_to_scan),
                              text=f"Lade {sym} ({i+1}/{len(symbols_to_scan)})")
            df = _load_chain(
                date=selected_date, symbol=sym,
                dte_min=dte_range[0], dte_max=dte_range[1],
                min_oi=min_oi, min_vol=min_vol,
            )
            if df.empty:
                continue
            rows = build_strategies(df, min_profit, max_risk, outlook, delta_short, delta_buy,
                                    max_delta=max_delta_val if use_max_delta else None,
                                    score_style=score_style)
            all_results.extend(rows)
        progress.empty()

        st.session_state.sf_results    = all_results
        st.session_state.sf_strategies = strategies
        st.session_state.sf_symbols    = symbols_to_scan
        st.session_state.sf_last_symbol = symbols_to_scan[0] if len(symbols_to_scan) == 1 else ""

    # ── Ergebnisse ────────────────────────────────────────────────────────────
    all_results  = st.session_state.get("sf_results", [])
    strat_filter = st.session_state.get("sf_strategies", strategies if run else [])
    filtered     = [s for s in all_results if s["Strategie"] in strat_filter]
    if exclude_earnings:
        filtered = [s for s in filtered if not s["_earnings_warn"]]
    if min_puffer > 0:
        filtered = [s for s in filtered if s["OTM %"] >= min_puffer]
    if only_overpriced:
        filtered = [s for s in filtered if s.get("_all_overpriced", False)]

    # Technische Filter (Score / RSI / Stoch / Langweiler)
    if min_tech_score > 0:
        # Iron Condor (tech_score None) neutral → durchlassen; sonst Score-Schwelle
        filtered = [s for s in filtered
                    if s.get("tech_score") is None or s["tech_score"] >= min_tech_score]
    _rsi_lo, _rsi_hi = rsi_range
    if _rsi_lo > 0 or _rsi_hi < 100:
        filtered = [s for s in filtered
                    if not _is_num(s.get("_rsi")) or (_rsi_lo <= s["_rsi"] <= _rsi_hi)]
    _st_lo, _st_hi = stoch_range
    if _st_lo > 0 or _st_hi < 100:
        filtered = [s for s in filtered
                    if not _is_num(s.get("_stoch_k")) or (_st_lo <= s["_stoch_k"] <= _st_hi)]
    if boring_only:
        def _boring(s) -> bool:
            beta = s.get("_beta"); mcap = s.get("_market_cap")
            sector = s.get("_company_sector"); iv = s.get("IV %", 0) / 100
            if not _is_num(beta) or beta > BORING_MAX_BETA:
                return False
            if iv > BORING_MAX_IV:
                return False
            if not _is_num(mcap) or mcap < BORING_MIN_MARKET_CAP:
                return False
            if sector not in BORING_SECTORS:
                return False
            return True
        filtered = [s for s in filtered if _boring(s)]

    if not filtered:
        if all_results:
            st.warning(f"Keine Treffer nach Filtern. Gesamt: {len(all_results)}. Kriterien lockern.")
        else:
            st.warning("Keine Optionsdaten gefunden. DTE-Fenster oder OI/Vol-Filter anpassen.")
        return

    # Zusammenfassung
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Symbole gescannt", len(st.session_state.get("sf_symbols", [])))
    m2.metric("Treffer gesamt", len(filtered))
    m3.metric("Strategien", len({s["Strategie"] for s in filtered}))
    m4.metric("Symbole mit Treffer", len({s["Symbol"] for s in filtered}))

    # Sortierung
    sc1, sc2 = st.columns([2, 6])
    sort_by = sc1.selectbox("Sortieren nach", ["RoR %", "Max Profit $", "DTE", "Symbol"], index=0)
    sort_asc = sort_by == "DTE"
    filtered.sort(key=lambda x: x[sort_by], reverse=not sort_asc)

    # Tabs nach Strategie-Typ + Alle
    seen_types = list(dict.fromkeys(s["Strategie"] for s in filtered))
    tab_labels = seen_types + ["Alle"]
    tabs = st.tabs(tab_labels)

    for i, tab in enumerate(tabs):
        with tab:
            subset = filtered if i == len(seen_types) else [s for s in filtered if s["Strategie"] == seen_types[i]]
            tab_key = "alle" if i == len(seen_types) else seen_types[i].replace(" ", "_")
            _render_table(subset, tab_key)

    # CSV-Export
    with st.expander("CSV Export"):
        export_rows = [dict(r) for r in filtered]
        for r in export_rows:
            ts = r.get("tech_score")
            r["Score"] = f"{int(ts)}/6" if _is_num(ts) else "–"
        df_export = pd.DataFrame(export_rows)[_DISPLAY_COLS]
        csv = df_export.to_csv(index=False).encode("utf-8")
        label = st.session_state.get("sf_last_symbol") or "scan"
        st.download_button("Download CSV", csv, f"strategies_{label}.csv", "text/csv")


if __name__ == "__main__":
    main()
