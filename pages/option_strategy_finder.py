"""Option Strategy Finder — Symbol oder Sektor -> Optionsstrategien im DTE-Fenster."""

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.streamlit_helpers import render_date_filter

# ── Delta-Konstanten (Defaults, werden per Slider überschrieben) ──────────────
_DELTA_SHORT_DEFAULT    = 0.30
_DELTA_SPREAD_BUY_DEF   = 0.15
MIN_OI_DEFAULT          = 50
MIN_VOL_DEFAULT         = 5


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
def _load_symbols_for_sector(sector: str) -> list[str]:
    df = select_into_dataframe(
        query="""
            SELECT DISTINCT o.symbol
            FROM "OptionDataMerged" o
            JOIN "FundamentalData" f ON f.symbol = o.symbol
            WHERE f.company_sector = :sector
            ORDER BY o.symbol ASC
        """,
        params={"sector": sector},
    )
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
                     outlook: str, delta_short: float, delta_buy: float) -> list[dict]:
    if df.empty:
        return []

    stock_price = df["stock_price"].iloc[0]
    symbol = df["symbol"].iloc[0] if "symbol" in df.columns else ""
    results: list[dict] = []

    puts  = df[df["option_type"] == "put"].copy()
    calls = df[df["option_type"] == "call"].copy()

    for exp_date, exp_puts in puts.groupby("expiration_date"):
        dte = int(exp_puts["dte"].iloc[0])
        exp_calls = calls[calls["expiration_date"] == exp_date]

        # Short Put
        if outlook in ("Bullish", "Neutral"):
            leg = _closest_delta(exp_puts, delta_short)
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
                    ))

        # Covered Call
        if outlook in ("Neutral", "Bearish") and not exp_calls.empty:
            leg = _closest_delta(exp_calls, delta_short)
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
                    ))

        # Bull Put Spread
        if outlook in ("Bullish", "Neutral") and len(exp_puts) >= 2:
            sell_leg = _closest_delta(exp_puts, delta_short)
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
                        ))

        # Bear Call Spread
        if outlook in ("Bearish", "Neutral") and len(exp_calls) >= 2:
            sell_leg = _closest_delta(exp_calls, delta_short)
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
                        ))

        # Iron Condor
        if outlook == "Neutral" and len(exp_puts) >= 2 and len(exp_calls) >= 2:
            put_sell  = _closest_delta(exp_puts,  delta_short)
            call_sell = _closest_delta(exp_calls, delta_short)
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
                        ))

    return results


def _row(strat, symbol, exp_date, dte, legs, kredit, max_profit, max_risk,
         breakeven, ror, delta, iv, iv_rank, otm_pct, earnings_date) -> dict:
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
    }


# ── Tabellen-Rendering ────────────────────────────────────────────────────────

_DISPLAY_COLS = [
    "Strategie", "Symbol", "Verfall", "DTE", "Beine",
    "Kredit $", "Max Profit $", "Max Risiko $", "RoR %",
    "Breakeven", "Delta", "IV %", "IV Rank", "OTM %",
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
    st.subheader(f"{s['Strategie']} — {s['Symbol']}")

    # Externe Links
    sym = s["Symbol"]
    lc1, lc2, lc3, lc4 = st.columns(4)
    lc1.link_button("TradingView", f"https://www.tradingview.com/chart/?symbol={sym}", use_container_width=True)
    lc2.link_button("Finviz", f"https://finviz.com/quote.ashx?t={sym}", use_container_width=True)
    lc3.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{sym}", use_container_width=True)
    lc4.link_button("Seeking Alpha", f"https://seekingalpha.com/symbol/{sym}", use_container_width=True)

    st.caption(f"Verfall: **{s['Verfall']}** · {s['DTE']} DTE")
    st.code(s["Beine"], language=None)

    if s["_earnings_warn"]:
        st.warning(f"Earnings vor Verfall ({s['earnings_date']}) — erhöhtes Gap-Risiko.")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Kredit",      f"${s['Kredit $']:.0f}")
    c2.metric("Max Profit",  f"${s['Max Profit $']:.0f}")
    c3.metric("Max Risiko",  f"${s['Max Risiko $']:.0f}")
    c4.metric("RoR %",       f"{s['RoR %']:.1f}%")
    c5.metric("Breakeven",   f"${s['Breakeven']:.2f}")

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Delta",   f"{s['Delta']:.2f}")
    c7.metric("IV %",    f"{s['IV %']:.1f}%")
    c8.metric("IV Rank", f"{s['IV Rank']:.0f}")
    c9.metric("OTM %",   f"{s['OTM %']:.1f}%")


def _render_table(rows: list[dict], tab_key: str):
    if not rows:
        st.info("Keine Treffer in dieser Kategorie.")
        return
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
    else:
        sectors = _load_sectors()
        chosen_sector = st.selectbox(
            "Sektor", [""] + sectors,
            index=0,
            placeholder="Sektor wählen...",
        )
        if chosen_sector:
            sector_symbols = _load_symbols_for_sector(chosen_sector)
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
            exclude_earnings = st.toggle("Earnings ausschließen", value=False,
                                         help="Alle Strategien ausblenden, bei denen Earnings vor dem Verfall liegen.")

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
            rows = build_strategies(df, min_profit, max_risk, outlook, delta_short, delta_buy)
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
        df_export = pd.DataFrame(filtered)[_DISPLAY_COLS]
        csv = df_export.to_csv(index=False).encode("utf-8")
        label = st.session_state.get("sf_last_symbol") or "scan"
        st.download_button("Download CSV", csv, f"strategies_{label}.csv", "text/csv")


if __name__ == "__main__":
    main()
