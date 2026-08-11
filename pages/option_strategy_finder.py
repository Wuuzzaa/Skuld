import streamlit as st
import pandas as pd
import numpy as np
from config import PATH_DATABASE_QUERY_FOLDER
from src.historization import select_timetravel_into_dataframe
from src.streamlit_helpers import render_date_filter

# ── Konstanten ────────────────────────────────────────────────────────────────
DELTA_SHORT_PUT   = 0.30
DELTA_SHORT_CALL  = 0.30
DELTA_SPREAD_SELL = 0.30
DELTA_SPREAD_BUY  = 0.15
MIN_OI_DEFAULT    = 50
MIN_VOL_DEFAULT   = 5


# ── Datenladen ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def load_chain(date: str, symbol: str, dte_min: int, dte_max: int,
               min_oi: int, min_vol: int) -> pd.DataFrame:
    sql_path = PATH_DATABASE_QUERY_FOLDER / "strategy_finder_chain.sql"
    df = select_timetravel_into_dataframe(
        date=date,
        sql_file_path=sql_path,
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
                "iv_rank", "hv_30d"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["dte"] = pd.to_numeric(df["dte"], errors="coerce")
    return df


# ── Strategie-Builder ─────────────────────────────────────────────────────────

def _closest_delta(sub: pd.DataFrame, target: float) -> pd.Series | None:
    if sub.empty:
        return None
    sub = sub.copy()
    sub["_dd"] = (sub["greeks_delta"].abs() - target).abs()
    return sub.loc[sub["_dd"].idxmin()]


def _color(val: float, good_above: float = 0) -> str:
    if val >= good_above * 1.5: return "🟢"
    if val >= good_above:       return "🟡"
    return "🔴"


def build_strategies(df: pd.DataFrame, min_profit: float, max_risk: float,
                     outlook: str) -> list[dict]:
    """Erzeugt alle passenden Strategie-Cards aus der Optionskette."""
    if df.empty:
        return []

    stock_price = df["stock_price"].iloc[0]
    results: list[dict] = []

    puts  = df[df["option_type"] == "put"].copy()
    calls = df[df["option_type"] == "call"].copy()

    for exp_date, exp_puts in puts.groupby("expiration_date"):
        dte   = int(exp_puts["dte"].iloc[0])
        exp_calls = calls[calls["expiration_date"] == exp_date]

        # ── 1. Short Put ──────────────────────────────────────────────────────
        if outlook in ("Bullish", "Neutral"):
            leg = _closest_delta(exp_puts, DELTA_SHORT_PUT)
            if leg is not None:
                credit = float(leg["premium"]) * 100
                risk   = float(leg["strike_price"]) * 100   # CSP-Risiko
                if credit >= min_profit and risk <= max_risk:
                    results.append({
                        "strategie":  "Short Put",
                        "symbol":     df["symbol"].iloc[0] if "symbol" in df.columns else "",
                        "expiration": exp_date,
                        "dte":        dte,
                        "legs":       f"Sell {leg['strike_price']:.2f}P",
                        "kredit":     credit,
                        "max_profit": credit,
                        "max_risk":   risk,
                        "breakeven":  float(leg["strike_price"]) - float(leg["premium"]),
                        "ror":        credit / risk * 100,
                        "delta":      float(leg["greeks_delta"]),
                        "iv":         float(leg["implied_volatility"]),
                        "iv_rank":    float(leg.get("iv_rank", 0) or 0),
                        "otm_pct":    (stock_price - float(leg["strike_price"])) / stock_price * 100,
                        "earnings_date": leg.get("earnings_date", None),
                        "dte_val":    dte,
                    })

        # ── 2. Covered Call ───────────────────────────────────────────────────
        if outlook in ("Neutral", "Bearish") and not exp_calls.empty:
            leg = _closest_delta(exp_calls, DELTA_SHORT_CALL)
            if leg is not None:
                credit = float(leg["premium"]) * 100
                if credit >= min_profit:
                    results.append({
                        "strategie":  "Covered Call",
                        "symbol":     df["symbol"].iloc[0] if "symbol" in df.columns else "",
                        "expiration": exp_date,
                        "dte":        dte,
                        "legs":       f"Sell {leg['strike_price']:.2f}C",
                        "kredit":     credit,
                        "max_profit": credit + (float(leg["strike_price"]) - stock_price) * 100,
                        "max_risk":   stock_price * 100,
                        "breakeven":  stock_price - float(leg["premium"]),
                        "ror":        credit / (stock_price * 100) * 100,
                        "delta":      float(leg["greeks_delta"]),
                        "iv":         float(leg["implied_volatility"]),
                        "iv_rank":    float(leg.get("iv_rank", 0) or 0),
                        "otm_pct":    (float(leg["strike_price"]) - stock_price) / stock_price * 100,
                        "earnings_date": leg.get("earnings_date", None),
                        "dte_val":    dte,
                    })

        # ── 3. Bull Put Spread ────────────────────────────────────────────────
        if outlook in ("Bullish", "Neutral") and len(exp_puts) >= 2:
            sell_leg = _closest_delta(exp_puts, DELTA_SPREAD_SELL)
            if sell_leg is not None:
                buy_candidates = exp_puts[
                    exp_puts["strike_price"] < sell_leg["strike_price"]
                ]
                buy_leg = _closest_delta(buy_candidates, DELTA_SPREAD_BUY)
                if buy_leg is not None:
                    width  = float(sell_leg["strike_price"]) - float(buy_leg["strike_price"])
                    credit = (float(sell_leg["premium"]) - float(buy_leg["premium"])) * 100
                    risk   = (width * 100) - credit
                    if credit >= min_profit and risk <= max_risk and credit > 0:
                        results.append({
                            "strategie":  "Bull Put Spread",
                            "symbol":     df["symbol"].iloc[0] if "symbol" in df.columns else "",
                            "expiration": exp_date,
                            "dte":        dte,
                            "legs":       f"Sell {sell_leg['strike_price']:.2f}P / Buy {buy_leg['strike_price']:.2f}P",
                            "kredit":     credit,
                            "max_profit": credit,
                            "max_risk":   risk,
                            "breakeven":  float(sell_leg["strike_price"]) - credit / 100,
                            "ror":        credit / risk * 100 if risk > 0 else 0,
                            "delta":      float(sell_leg["greeks_delta"]),
                            "iv":         float(sell_leg["implied_volatility"]),
                            "iv_rank":    float(sell_leg.get("iv_rank", 0) or 0),
                            "otm_pct":    (stock_price - float(sell_leg["strike_price"])) / stock_price * 100,
                            "earnings_date": sell_leg.get("earnings_date", None),
                            "dte_val":    dte,
                        })

        # ── 4. Bear Call Spread ───────────────────────────────────────────────
        if outlook in ("Bearish", "Neutral") and len(exp_calls) >= 2:
            sell_leg = _closest_delta(exp_calls, DELTA_SPREAD_SELL)
            if sell_leg is not None:
                buy_candidates = exp_calls[
                    exp_calls["strike_price"] > sell_leg["strike_price"]
                ]
                buy_leg = _closest_delta(buy_candidates, DELTA_SPREAD_BUY)
                if buy_leg is not None:
                    width  = float(buy_leg["strike_price"]) - float(sell_leg["strike_price"])
                    credit = (float(sell_leg["premium"]) - float(buy_leg["premium"])) * 100
                    risk   = (width * 100) - credit
                    if credit >= min_profit and risk <= max_risk and credit > 0:
                        results.append({
                            "strategie":  "Bear Call Spread",
                            "symbol":     df["symbol"].iloc[0] if "symbol" in df.columns else "",
                            "expiration": exp_date,
                            "dte":        dte,
                            "legs":       f"Sell {sell_leg['strike_price']:.2f}C / Buy {buy_leg['strike_price']:.2f}C",
                            "kredit":     credit,
                            "max_profit": credit,
                            "max_risk":   risk,
                            "breakeven":  float(sell_leg["strike_price"]) + credit / 100,
                            "ror":        credit / risk * 100 if risk > 0 else 0,
                            "delta":      float(sell_leg["greeks_delta"]),
                            "iv":         float(sell_leg["implied_volatility"]),
                            "iv_rank":    float(sell_leg.get("iv_rank", 0) or 0),
                            "otm_pct":    (float(sell_leg["strike_price"]) - stock_price) / stock_price * 100,
                            "earnings_date": sell_leg.get("earnings_date", None),
                            "dte_val":    dte,
                        })

        # ── 5. Iron Condor = Bull Put Spread + Bear Call Spread ───────────────
        if outlook == "Neutral" and len(exp_puts) >= 2 and len(exp_calls) >= 2:
            put_sell  = _closest_delta(exp_puts,  DELTA_SPREAD_SELL)
            call_sell = _closest_delta(exp_calls, DELTA_SPREAD_SELL)
            if put_sell is not None and call_sell is not None:
                put_buys  = exp_puts[exp_puts["strike_price"] < put_sell["strike_price"]]
                call_buys = exp_calls[exp_calls["strike_price"] > call_sell["strike_price"]]
                put_buy   = _closest_delta(put_buys,  DELTA_SPREAD_BUY)
                call_buy  = _closest_delta(call_buys, DELTA_SPREAD_BUY)
                if put_buy is not None and call_buy is not None:
                    put_width  = float(put_sell["strike_price"])  - float(put_buy["strike_price"])
                    call_width = float(call_buy["strike_price"])  - float(call_sell["strike_price"])
                    put_cr  = (float(put_sell["premium"])  - float(put_buy["premium"]))  * 100
                    call_cr = (float(call_sell["premium"]) - float(call_buy["premium"])) * 100
                    total_credit = put_cr + call_cr
                    max_risk_ic  = max(put_width, call_width) * 100 - total_credit
                    if total_credit >= min_profit and max_risk_ic <= max_risk and total_credit > 0:
                        results.append({
                            "strategie":  "Iron Condor",
                            "symbol":     df["symbol"].iloc[0] if "symbol" in df.columns else "",
                            "expiration": exp_date,
                            "dte":        dte,
                            "legs": (
                                f"Sell {put_sell['strike_price']:.2f}P / Buy {put_buy['strike_price']:.2f}P  |  "
                                f"Sell {call_sell['strike_price']:.2f}C / Buy {call_buy['strike_price']:.2f}C"
                            ),
                            "kredit":     total_credit,
                            "max_profit": total_credit,
                            "max_risk":   max_risk_ic,
                            "breakeven":  float(put_sell["strike_price"]) - total_credit / 100,
                            "ror":        total_credit / max_risk_ic * 100 if max_risk_ic > 0 else 0,
                            "delta":      float(put_sell["greeks_delta"]),
                            "iv":         float(put_sell["implied_volatility"]),
                            "iv_rank":    float(put_sell.get("iv_rank", 0) or 0),
                            "otm_pct":    (stock_price - float(put_sell["strike_price"])) / stock_price * 100,
                            "earnings_date": put_sell.get("earnings_date", None),
                            "dte_val":    dte,
                        })

    return results


# ── Card-Rendering ─────────────────────────────────────────────────────────────

STRATEGY_ICONS = {
    "Short Put":       "📉",
    "Covered Call":    "📞",
    "Bull Put Spread": "🟢",
    "Bear Call Spread":"🔴",
    "Iron Condor":     "🦅",
}

def _earnings_warning(s: dict, stock_price: float) -> str:
    ed = s.get("earnings_date")
    if ed is None or pd.isna(ed):
        return ""
    try:
        import datetime
        exp = pd.to_datetime(s["expiration"]).date()
        ear = pd.to_datetime(ed).date()
        if ear <= exp:
            return f"⚠️ Earnings vor Verfall ({ear})"
    except Exception:
        pass
    return ""

def render_card(s: dict, stock_price: float):
    icon = STRATEGY_ICONS.get(s["strategie"], "🔹")
    ror_color  = _color(s["ror"],  good_above=5)
    iv_color   = "🟢" if 35 <= s["iv_rank"] <= 65 else ("🟡" if 20 <= s["iv_rank"] <= 80 else "🔴")
    earn_warn  = _earnings_warning(s, stock_price)

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            st.markdown(f"### {icon} {s['strategie']}")
            st.caption(f"**{s['expiration']}** · {s['dte']} DTE")
            st.code(s["legs"], language=None)
            if earn_warn:
                st.warning(earn_warn, icon="⚠️")
        with c2:
            st.metric("Max Profit",  f"${s['max_profit']:.0f}")
            st.metric("Max Risiko",  f"${s['max_risk']:.0f}")
            st.metric("Breakeven",   f"${s['breakeven']:.2f}")
        with c3:
            st.markdown(f"**RoR:** {ror_color} {s['ror']:.1f}%")
            st.markdown(f"**Delta:** {s['delta']:.2f}")
            st.markdown(f"**IV:** {s['iv']:.1%}")
            st.markdown(f"**IV Rank:** {iv_color} {s['iv_rank']:.0f}%")
            otm_label = "OTM" if s["otm_pct"] > 0 else "ITM"
            st.markdown(f"**{otm_label}:** {abs(s['otm_pct']):.1f}%")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("🔭 Option Strategy Finder")
    st.write("Symbol eingeben → alle sinnvollen Strategien im gewählten DTE-Fenster.")

    selected_date = render_date_filter(
        date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
    )

    # ── Eingabe ───────────────────────────────────────────────────────────────
    with st.form("finder_form"):
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            symbol  = st.text_input("Symbol", value="AAPL", placeholder="z.B. AAPL, MSFT, SPY").upper().strip()
            outlook = st.radio("Marktmeinung", ["Bullish", "Neutral", "Bearish"], index=1, horizontal=True)
        with col2:
            dte_range  = st.slider("DTE-Fenster", min_value=0, max_value=120, value=(21, 60))
            min_profit = st.number_input("Min. Profit / Kredit ($)", min_value=0, max_value=10000, value=50, step=10)
            max_risk   = st.number_input("Max. Risiko ($)", min_value=100, max_value=500000, value=2000, step=100)
        with col3:
            min_oi  = st.number_input("Min. Open Interest", min_value=0, max_value=10000, value=MIN_OI_DEFAULT, step=10)
            min_vol = st.number_input("Min. Tagesvolumen", min_value=0, max_value=10000, value=MIN_VOL_DEFAULT, step=1)
            strategies = st.multiselect(
                "Strategien anzeigen",
                ["Short Put", "Covered Call", "Bull Put Spread", "Bear Call Spread", "Iron Condor"],
                default=["Short Put", "Bull Put Spread", "Iron Condor"],
            )
        submitted = st.form_submit_button("🔍 Strategien suchen", use_container_width=True, type="primary")

    if not submitted and "sf_results" not in st.session_state:
        st.info("Symbol eingeben und auf **Strategien suchen** klicken.")
        return

    if submitted:
        if not symbol:
            st.error("Bitte ein Symbol eingeben.")
            return
        with st.spinner(f"Lade Optionskette für **{symbol}** …"):
            df = load_chain(
                date=selected_date,
                symbol=symbol,
                dte_min=dte_range[0],
                dte_max=dte_range[1],
                min_oi=min_oi,
                min_vol=min_vol,
            )
        if df.empty:
            st.warning(f"Keine Optionsdaten für **{symbol}** im DTE-Bereich {dte_range[0]}–{dte_range[1]} gefunden.")
            st.session_state.sf_results = []
            st.session_state.sf_symbol  = symbol
            return

        stock_price = float(df["stock_price"].iloc[0])
        all_strategies = build_strategies(df, min_profit, max_risk, outlook)
        st.session_state.sf_results    = all_strategies
        st.session_state.sf_symbol     = symbol
        st.session_state.sf_stock      = stock_price
        st.session_state.sf_strategies = strategies
        st.session_state.sf_df         = df

    # ── Ergebnisse ────────────────────────────────────────────────────────────
    all_results  = st.session_state.get("sf_results", [])
    symbol_saved = st.session_state.get("sf_symbol", symbol)
    stock_price  = st.session_state.get("sf_stock", 0.0)
    strat_filter = st.session_state.get("sf_strategies", strategies if submitted else [])
    df_saved     = st.session_state.get("sf_df", pd.DataFrame())

    filtered = [s for s in all_results if s["strategie"] in strat_filter]

    if not df_saved.empty:
        info_cols = st.columns(4)
        with info_cols[0]:
            st.metric("Symbol", symbol_saved)
        with info_cols[1]:
            st.metric("Aktueller Kurs", f"${stock_price:.2f}")
        with info_cols[2]:
            iv_rank_val = float(df_saved["iv_rank"].dropna().iloc[0]) if not df_saved["iv_rank"].dropna().empty else 0
            st.metric("IV Rank", f"{iv_rank_val:.0f}%")
        with info_cols[3]:
            st.metric("Strategien gefunden", len(filtered))

    if not filtered:
        if all_results:
            st.warning(f"Keine Strategien nach Filtern übrig. Gesamt gefunden: {len(all_results)}. Kriterien lockern (Min. Profit ↓ / Max. Risiko ↑).")
        return

    # Sortierung
    sort_col, _ = st.columns([2, 6])
    with sort_col:
        sort_by = st.selectbox("Sortieren nach", ["Max Profit ($)", "Return on Risk (%)", "DTE"], index=1)

    sort_map = {"Max Profit ($)": "max_profit", "Return on Risk (%)": "ror", "DTE": "dte_val"}
    filtered.sort(key=lambda x: x[sort_map[sort_by]], reverse=True)

    # Gruppen nach Strategie-Typ
    seen_types = []
    for s in filtered:
        if s["strategie"] not in seen_types:
            seen_types.append(s["strategie"])

    tab_labels = seen_types + ["📋 Alle"]
    tabs = st.tabs(tab_labels)

    for i, tab in enumerate(tabs):
        with tab:
            if i < len(seen_types):
                subset = [s for s in filtered if s["strategie"] == seen_types[i]]
            else:
                subset = filtered

            if not subset:
                st.info("Keine Einträge in dieser Kategorie.")
                continue

            for s in subset:
                render_card(s, stock_price)

    # Tabellen-Export
    with st.expander("📊 Alle Ergebnisse als Tabelle"):
        export_cols = ["strategie", "expiration", "dte", "legs",
                       "max_profit", "max_risk", "ror", "breakeven",
                       "delta", "iv", "iv_rank", "otm_pct"]
        df_export = pd.DataFrame(filtered)[export_cols].copy()
        df_export.columns = ["Strategie", "Verfall", "DTE", "Beine",
                             "Max Profit $", "Max Risiko $", "RoR %",
                             "Breakeven", "Delta", "IV", "IV Rank %", "OTM %"]
        st.dataframe(
            df_export.style.format({
                "Max Profit $": "{:.0f}", "Max Risiko $": "{:.0f}",
                "RoR %": "{:.1f}", "Breakeven": "{:.2f}",
                "Delta": "{:.2f}", "IV": "{:.1%}", "IV Rank %": "{:.0f}",
                "OTM %": "{:.1f}",
            }),
            use_container_width=True,
        )
        csv = df_export.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ CSV Download", csv, f"strategies_{symbol_saved}.csv", "text/csv")


if __name__ == "__main__":
    main()
