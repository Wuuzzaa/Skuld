"""Crash Hedge Finder — On-the-fly Korrelation + Prämienverkauf auf Gegenwerte."""

import io
import csv
import re
import logging
import os

import numpy as np
import pandas as pd
import streamlit as st

from src.database import select_into_dataframe
from src.page_display_dataframe import create_claude_prompt_strategy_finder

logger = logging.getLogger(os.path.basename(__file__))

_KNOWN_HEDGES = ["GLD", "SLV", "TLT", "IEF", "XLU", "XLP", "XLV", "VXX"]
_DTE_MIN_DEFAULT  = 21
_DTE_MAX_DEFAULT  = 60
_MIN_NEG_CORR     = -0.20
_MIN_IV_RANK      = 30.0
_MIN_OI           = 50
_MIN_CREDIT       = 30
_MIN_MARKET_CAP_B = 10.0   # ≥ $10 Mrd


# ── CSV-Import ────────────────────────────────────────────────────────────────

def _parse_ibkr_csv(content: str) -> list[dict]:
    positions = []
    reader = csv.reader(io.StringIO(content))
    mtm_header: list[str] = []
    for row in reader:
        if not row:
            continue
        if row[0].strip() != "Mark-to-Market-Performance-Überblick":
            continue
        record_type = row[1].strip() if len(row) > 1 else ""
        if record_type == "Header":
            mtm_header = [c.strip() for c in row[2:]]
            continue
        if record_type != "Data" or not mtm_header:
            continue
        data = dict(zip(mtm_header, row[2:]))
        asset_class = data.get("Vermögenswertkategorie", "").strip()
        symbol_raw  = data.get("Symbol", "").strip()
        try:
            qty_now = float(data.get("Aktuell Menge", "0") or "0")
        except ValueError:
            continue
        if qty_now == 0:
            continue
        if asset_class == "Aktien":
            positions.append({"type": "stock", "symbol": symbol_raw,
                               "qty": int(abs(qty_now)),
                               "direction": "Long" if qty_now > 0 else "Short"})
        elif asset_class == "Aktien- und Indexoptionen":
            m = re.match(r"^([A-Z0-9]+)\s+(\d{2}[A-Z]{3}\d{2})\s+([\d.]+)\s+([CP])$", symbol_raw)
            if not m:
                continue
            sym, expiry_raw, strike_str, cp = m.groups()
            try:
                from datetime import datetime
                expiry = datetime.strptime(expiry_raw, "%d%b%y").strftime("%Y-%m-%d")
            except ValueError:
                expiry = expiry_raw
            positions.append({"type": "option", "symbol": sym,
                               "contract_type": "call" if cp == "C" else "put",
                               "strike": float(strike_str), "expiry": expiry,
                               "contracts": int(abs(qty_now)),
                               "direction": "Long" if qty_now > 0 else "Short"})
    return positions


# ── Datenbankabfragen ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_large_cap_symbols(min_market_cap_b: float) -> list[str]:
    """Alle Symbole aus OptionDataMerged mit Market Cap ≥ Schwelle."""
    df = select_into_dataframe(
        query="""
            SELECT DISTINCT symbol
            FROM "OptionDataMerged"
            WHERE "Summary_marketCap" >= :min_mcap
            ORDER BY symbol
        """,
        params={"min_mcap": min_market_cap_b * 1_000_000_000},
    )
    if df is None or df.empty:
        return []
    known = set(_KNOWN_HEDGES)
    syms = df["symbol"].dropna().astype(str).tolist()
    # Immer bekannte Hedge-Symbole ergänzen, auch wenn Market Cap fehlt
    for s in _KNOWN_HEDGES:
        if s not in syms:
            syms.append(s)
    return syms


@st.cache_data(ttl=3600, show_spinner=False)
def _load_prices_for_symbols(symbols: tuple[str, ...], lookback_days: int) -> pd.DataFrame:
    """
    Lädt Tagesschlusskurse für die gegebenen Symbole on-the-fly.
    Gibt Wide-DataFrame zurück: Index=Datum, Columns=Symbole.
    """
    if not symbols:
        return pd.DataFrame()
    df = select_into_dataframe(
        query="""
            SELECT symbol, snapshot_date, close
            FROM "StockPricesYahooHistoryDaily"
            WHERE symbol = ANY(:syms)
              AND snapshot_date >= CURRENT_DATE - CAST(:lb || ' days' AS INTERVAL)
              AND close IS NOT NULL
            ORDER BY snapshot_date
        """,
        params={"syms": list(symbols), "lb": str(lookback_days)},
    )
    if df is None or df.empty:
        return pd.DataFrame()
    pivot = df.pivot(index="snapshot_date", columns="symbol", values="close")
    min_pts = int(pivot.shape[0] * 0.7)
    pivot = pivot.dropna(axis=1, thresh=min_pts).ffill()
    return pivot


@st.cache_data(ttl=600, show_spinner=False)
def _load_option_candidates(symbols: tuple[str, ...], dte_min: int, dte_max: int,
                             min_oi: int) -> pd.DataFrame:
    if not symbols:
        return pd.DataFrame()
    df = select_into_dataframe(
        query="""
            SELECT
                symbol, option_type, strike_price,
                day_close          AS premium,
                greeks_delta,
                implied_volatility AS iv,
                iv_rank,
                open_interest,
                expiration_date,
                days_to_expiration AS dte,
                live_stock_price   AS stock_price,
                company_name,
                company_sector
            FROM "OptionDataMerged"
            WHERE symbol = ANY(:syms)
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND open_interest >= :min_oi
              AND day_close > 0
        """,
        params={"syms": list(symbols), "dte_min": dte_min,
                "dte_max": dte_max, "min_oi": min_oi},
    )
    return df if df is not None else pd.DataFrame()


# ── Korrelationsberechnung on-the-fly ─────────────────────────────────────────

def _compute_correlations(portfolio_symbols: list[str], universe_symbols: list[str],
                           lookback_days: int) -> pd.DataFrame:
    """
    Berechnet Ø-Korrelation jedes Universe-Symbols vs. allen Portfolio-Symbolen.
    Gibt DataFrame [peer_symbol, correlation_mean] zurück, sortiert aufsteigend.
    """
    all_syms = tuple(sorted(set(portfolio_symbols) | set(universe_symbols)))
    prices = _load_prices_for_symbols(all_syms, lookback_days)

    if prices.empty:
        return pd.DataFrame()

    returns = prices.pct_change().dropna(how="all")

    port_cols  = [s for s in portfolio_symbols if s in returns.columns]
    peer_cols  = [s for s in universe_symbols  if s in returns.columns
                  and s not in portfolio_symbols]

    if not port_cols or not peer_cols:
        return pd.DataFrame()

    # Korrelation jedes Peers gegen alle Portfolio-Symbole → Durchschnitt
    port_ret  = returns[port_cols]
    peer_ret  = returns[peer_cols]
    corr_full = peer_ret.corrwith(port_ret.mean(axis=1), method="pearson")

    result = (
        corr_full
        .rename("correlation_mean")
        .reset_index()
        .rename(columns={"index": "peer_symbol", "symbol": "peer_symbol"})
    )
    result.columns = ["peer_symbol", "correlation_mean"]
    result = result.dropna().sort_values("correlation_mean")
    return result


# ── Strategie-Builder ─────────────────────────────────────────────────────────

def _build_short_put_candidates(opt_df: pd.DataFrame, corr_map: dict,
                                 min_credit: float, min_iv_rank: float) -> list[dict]:
    results = []
    puts = opt_df[opt_df["option_type"] == "put"].copy()
    for col in ["strike_price", "premium", "greeks_delta", "iv", "iv_rank",
                "open_interest", "dte", "stock_price"]:
        puts[col] = pd.to_numeric(puts[col], errors="coerce")
    puts = puts.dropna(subset=["premium", "greeks_delta", "iv_rank", "stock_price"])

    for (sym, exp), group in puts.groupby(["symbol", "expiration_date"]):
        group = group.copy()
        group["_dd"] = (group["greeks_delta"].abs() - 0.30).abs()
        leg = group.loc[group["_dd"].idxmin()]

        stock_price = float(leg["stock_price"])
        strike      = float(leg["strike_price"])
        premium     = float(leg["premium"])
        credit      = premium * 100
        risk        = strike * 100
        iv_rank     = float(leg["iv_rank"])
        dte         = int(leg["dte"])
        iv          = float(leg["iv"])

        if credit < min_credit or risk <= 0 or iv_rank < min_iv_rank:
            continue

        ror  = credit / risk * 100
        otm  = (stock_price - strike) / stock_price * 100
        corr = corr_map.get(sym, 0.0)
        hedge_score = round(abs(corr) * ror, 2)

        results.append({
            "Strategie":     "Short Put",
            "Symbol":        sym,
            "Verfall":       str(exp),
            "DTE":           dte,
            "Beine":         f"Sell {strike:.2f}P",
            "Kredit $":      round(credit, 0),
            "Max Profit $":  round(credit, 0),
            "Max Risiko $":  round(risk, 0),
            "RoR %":         round(ror, 1),
            "Breakeven":     round(strike - premium, 2),
            "Delta":         round(float(leg["greeks_delta"]), 2),
            "IV %":          round(iv * 100, 1),
            "IV Rank":       round(iv_rank, 0),
            "OTM %":         round(otm, 1),
            "Korrelation":   round(corr, 3),
            "Hedge Score":   hedge_score,
            "_stock_price":  stock_price,
            "_company_name": str(leg.get("company_name") or sym),
            "_company_sector": str(leg.get("company_sector") or ""),
            "_legs": [{
                "type": "Put", "action": "Short",
                "strike": strike, "premium": premium, "bs": None,
                "delta": float(leg["greeks_delta"]), "iv": iv,
                "theta": 0.0, "oi": int(leg.get("open_interest") or 0), "volume": 0,
            }],
            "_earnings_warn": False,
        })
    return results


# ── Rendering ─────────────────────────────────────────────────────────────────

_DISPLAY_COLS = [
    "Symbol", "Strategie", "Verfall", "DTE", "Beine",
    "Kredit $", "RoR %", "IV Rank", "Korrelation", "Hedge Score", "OTM %",
]


def _style_table(df: pd.DataFrame):
    def _ror(col):
        return ["color:#34d399;font-weight:700" if v >= 15
                else ("color:#f59e0b;font-weight:700" if v >= 8 else "color:#ef4444")
                for v in col]
    def _corr(col):
        return ["color:#34d399;font-weight:700" if v <= -0.4
                else ("color:#f59e0b" if v <= -0.2 else "color:#94a3b8")
                for v in col]
    def _ivr(col):
        return ["color:#34d399;font-weight:700" if 35 <= v <= 65
                else ("color:#f59e0b" if 20 <= v <= 80 else "color:#ef4444")
                for v in col]
    return (
        df.style
        .apply(_ror,  subset=["RoR %"])
        .apply(_corr, subset=["Korrelation"])
        .apply(_ivr,  subset=["IV Rank"])
        .format({
            "Kredit $":    "{:.0f}",
            "RoR %":       "{:.1f}",
            "IV Rank":     "{:.0f}",
            "Korrelation": "{:.3f}",
            "Hedge Score": "{:.2f}",
            "OTM %":       "{:.1f}",
        })
    )


def _render_detail(row: dict):
    st.divider()
    ror   = row["RoR %"]
    corr  = row["Korrelation"]
    color = "#34d399" if ror >= 15 else ("#f59e0b" if ror >= 8 else "#ef4444")
    c_col = "#34d399" if corr <= -0.4 else ("#f59e0b" if corr <= -0.2 else "#94a3b8")
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;flex-wrap:wrap'>"
        f"<span style='font-size:20px;font-weight:700;'>{row['Strategie']} — {row['Symbol']}</span>"
        f"<span style='background:{color}22;border:1px solid {color}66;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;font-weight:700;color:{color};'>RoR {ror:.1f}%</span>"
        f"<span style='background:{c_col}22;border:1px solid {c_col}66;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;font-weight:600;color:{c_col};'>Korr. {corr:.3f}</span>"
        f"<span style='background:#1e293b;border:1px solid #334155;border-radius:20px;"
        f"padding:3px 14px;font-size:13px;color:#94a3b8;'>Kurs ${row['_stock_price']:.2f}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.caption(f"Verfall: **{row['Verfall']}** · {row['DTE']} DTE · "
               f"Hedge Score: **{row['Hedge Score']:.2f}** (|Korr.| × RoR)")
    st.code(row["Beine"], language=None)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kredit",     f"${row['Kredit $']:.0f}")
    c2.metric("Max Risiko", f"${row['Max Risiko $']:.0f}")
    c3.metric("IV Rank",    f"{row['IV Rank']:.0f}")
    c4.metric("Breakeven",  f"${row['Breakeven']:.2f}")
    claude_url = create_claude_prompt_strategy_finder(row, sector=row.get("_company_sector"))
    st.link_button("Claude AI Analyse", claude_url, type="primary", use_container_width=True)


def _render_portfolio_heatmap(portfolio_symbols: list[str], lookback_days: int):
    if len(portfolio_symbols) < 2:
        st.info("Mindestens 2 Symbole für die Heatmap.")
        return
    prices = _load_prices_for_symbols(tuple(sorted(portfolio_symbols)), lookback_days)
    if prices.empty:
        st.warning("Keine Preishistorie für die Portfolio-Symbole gefunden.")
        return
    available = [s for s in portfolio_symbols if s in prices.columns]
    if len(available) < 2:
        st.warning("Zu wenige Symbole mit Preishistorie für die Heatmap.")
        return
    returns = prices[available].pct_change().dropna(how="all")
    matrix  = returns.corr(method="pearson")
    styled  = (
        matrix.style
        .background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1)
        .format("{:.2f}")
    )
    st.dataframe(styled, use_container_width=True)
    pairs = [(a, b) for a in available for b in available
             if a < b and matrix.loc[a, b] >= 0.7]
    if pairs:
        pair_strs = ", ".join(f"{a}/{b}" for a, b in pairs[:5])
        st.warning(f"Klumpenrisiko: {pair_strs} korrelieren ≥ 0.70")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("Crash Hedge Finder")
    st.caption(
        "Portfolio eingeben → Korrelation gegen Large-Caps berechnen → "
        "Optionsstrategien auf negativ-korrelierte Gegenwerte finden."
    )

    # ── Schritt 1: Portfolio eingeben ─────────────────────────────────────────
    with st.container(border=True):
        col_csv, col_manual = st.columns([1, 1], gap="large")

        with col_csv:
            st.markdown("**CSV-Import (CapTrader / IBKR)**")
            st.caption("Activity Statement → Format CSV → Sektion 'Mark-to-Market Performance'")
            uploaded = st.file_uploader("CSV hochladen", type=["csv"], key="chf_csv",
                                        label_visibility="collapsed")
            if uploaded is not None:
                content  = uploaded.read().decode("utf-8", errors="replace")
                imported = _parse_ibkr_csv(content)
                if imported:
                    st.session_state["chf_positions"] = imported
                    st.success(f"{len(imported)} Positionen importiert.")
                else:
                    st.error("Keine Positionen gefunden — prüfe ob die CSV die "
                             "'Mark-to-Market-Performance-Überblick' Sektion enthält.")

        with col_manual:
            st.markdown("**Symbole manuell eingeben**")
            st.caption("Kommagetrennt, z.B. AAPL, MSFT, NVDA")
            manual_input = st.text_input(
                "Symbole", placeholder="AAPL, MSFT, NVDA, AMZN",
                key="chf_manual", label_visibility="collapsed"
            )
            if st.button("Übernehmen", key="chf_manual_btn") and manual_input:
                syms = [s.strip().upper() for s in manual_input.split(",") if s.strip()]
                st.session_state["chf_positions"] = [
                    {"type": "stock", "symbol": s, "qty": 100, "direction": "Long"}
                    for s in syms
                ]
                st.success(f"{len(syms)} Symbole übernommen.")

    positions: list[dict] = st.session_state.get("chf_positions", [])
    if not positions:
        st.info("Portfolio hochladen oder Symbole eingeben um fortzufahren.")
        return

    portfolio_symbols = sorted({
        p["symbol"] for p in positions
        if p.get("direction", "Long") == "Long"
    })

    st.markdown(
        f"**Portfolio ({len(portfolio_symbols)} Symbole):** "
        + "  ".join(f"`{s}`" for s in portfolio_symbols)
    )

    # ── Parameter ─────────────────────────────────────────────────────────────
    with st.expander("Parameter", expanded=False):
        p1, p2, p3 = st.columns(3)
        with p1:
            lookback_days = st.selectbox(
                "Korrelations-Lookback", [63, 126, 252, 504, 756, 1260],
                index=2,
                format_func=lambda x: {
                    63:   "3 Monate",
                    126:  "6 Monate",
                    252:  "1 Jahr",
                    504:  "2 Jahre",
                    756:  "3 Jahre",
                    1260: "5 Jahre",
                }[x],
            )
            min_neg_corr = st.slider(
                "Max. Korrelation (Schwelle)", -1.0, 0.0, _MIN_NEG_CORR, 0.05,
            )
        with p2:
            dte_range    = st.slider("DTE-Fenster", 7, 120, (_DTE_MIN_DEFAULT, _DTE_MAX_DEFAULT))
            min_iv_rank  = st.slider("Min. IV Rank", 0, 100, int(_MIN_IV_RANK), 5)
        with p3:
            min_credit   = st.number_input("Min. Kredit ($)", 0, 5000, _MIN_CREDIT, 10)
            min_oi       = st.number_input("Min. Open Interest", 0, 10000, _MIN_OI, 10)
            top_n        = st.slider("Top N Gegenwerte", 5, 50, 20, 5)

    # ── Suche-Button ──────────────────────────────────────────────────────────
    run = st.button("Hedge-Kandidaten suchen", type="primary", use_container_width=True)

    if not run and "chf_results" not in st.session_state:
        return

    if run:
        with st.status("Berechne Korrelationen...", expanded=True) as status:
            st.write(f"Lade Large-Cap Universum (≥ ${_MIN_MARKET_CAP_B:.0f} Mrd)...")
            universe = _load_large_cap_symbols(_MIN_MARKET_CAP_B)
            st.write(f"→ {len(universe)} Symbole im Universum")

            st.write(f"Lade Preishistorie ({lookback_days} Tage) für Portfolio + Universum...")
            corr_df = _compute_correlations(portfolio_symbols, universe, lookback_days)

            if corr_df is None or corr_df.empty:
                status.update(label="Fehler", state="error")
                st.error("Keine Preishistorie gefunden.")
                return

            neg_corr = corr_df[corr_df["correlation_mean"] <= min_neg_corr].head(top_n)
            # Bekannte Hedge-Symbole immer ergänzen
            extra = [s for s in _KNOWN_HEDGES if s not in neg_corr["peer_symbol"].values]
            if extra:
                extra_df = corr_df[corr_df["peer_symbol"].isin(extra)]
                neg_corr = pd.concat([neg_corr, extra_df], ignore_index=True).drop_duplicates("peer_symbol")

            st.write(f"→ {len(neg_corr)} negativ-korrelierte Gegenwerte gefunden")

            if neg_corr.empty:
                status.update(label="Keine Gegenwerte gefunden", state="error")
                st.warning("Keine negativ-korrelierten Symbole — Schwelle erhöhen oder Lookback ändern.")
                return

            corr_map = dict(zip(neg_corr["peer_symbol"], neg_corr["correlation_mean"]))
            candidate_symbols = tuple(neg_corr["peer_symbol"].tolist())

            st.write(f"Lade Optionsdaten für {len(candidate_symbols)} Gegenwerte...")
            opt_df = _load_option_candidates(candidate_symbols, dte_range[0], dte_range[1], min_oi)

            if opt_df is None or opt_df.empty:
                status.update(label="Keine Optionsdaten", state="error")
                st.warning("Keine Optionsdaten — DTE-Fenster oder OI-Filter anpassen.")
                return

            results = _build_short_put_candidates(opt_df, corr_map, min_credit, min_iv_rank)
            results.sort(key=lambda x: x["Hedge Score"], reverse=True)
            st.write(f"→ {len(results)} Strategien berechnet")
            status.update(label="Fertig", state="complete", expanded=False)

        st.session_state["chf_results"]   = results
        st.session_state["chf_corr_df"]   = neg_corr
        st.session_state["chf_portfolio"] = portfolio_symbols
        st.session_state["chf_lookback"]  = lookback_days

    # ── Ergebnisse ────────────────────────────────────────────────────────────
    results        = st.session_state.get("chf_results", [])
    neg_corr       = st.session_state.get("chf_corr_df", pd.DataFrame())
    portfolio_syms = st.session_state.get("chf_portfolio", portfolio_symbols)
    lb             = st.session_state.get("chf_lookback", lookback_days)

    tab_heatmap, tab_corr, tab_strategies = st.tabs([
        "Portfolio-Matrix", "Negativ-Korrelierte", "Hedge-Strategien"
    ])

    with tab_heatmap:
        st.caption("Rot = hohes Klumpenrisiko · Grün = gut diversifiziert")
        _render_portfolio_heatmap(portfolio_syms, lb)

    with tab_corr:
        st.caption("Gegenwerte mit negativer Korrelation zu deinem Portfolio")
        if not neg_corr.empty:
            styled_corr = (
                neg_corr
                .rename(columns={"peer_symbol": "Symbol", "correlation_mean": "Korrelation (Ø)"})
                .style
                .background_gradient(subset=["Korrelation (Ø)"], cmap="RdYlGn", vmin=-1, vmax=0)
                .format({"Korrelation (Ø)": "{:.3f}"})
            )
            st.dataframe(styled_corr, hide_index=True, use_container_width=True)

    with tab_strategies:
        if not results:
            st.info("Keine Strategien — Parameter lockern.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Kandidaten",       len({r["Symbol"] for r in results}))
            m2.metric("Strategien",        len(results))
            m3.metric("Bester Hedge Score", f"{results[0]['Hedge Score']:.2f}")
            m4.metric("Bester RoR",         f"{results[0]['RoR %']:.1f}%")

            df_disp = pd.DataFrame(results)[_DISPLAY_COLS].copy()
            event = st.dataframe(
                _style_table(df_disp),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="chf_table",
                column_config={
                    "Beine":       st.column_config.TextColumn("Beine", width="medium"),
                    "Kredit $":    st.column_config.NumberColumn("Kredit $",    format="$%.0f"),
                    "Korrelation": st.column_config.NumberColumn("Korrelation", format="%.3f"),
                    "Hedge Score": st.column_config.NumberColumn("Hedge Score", format="%.2f"),
                },
            )
            sel = event.selection.rows if hasattr(event, "selection") else []
            if sel:
                _render_detail(results[sel[0]])
            else:
                st.caption(
                    "Zeile anklicken für Details + Claude-Analyse. "
                    "**Hedge Score** = |Korrelation| × RoR%"
                )

            with st.expander("Wie funktioniert der Hedge Score?"):
                st.markdown("""
**Hedge Score = |Korrelation| × RoR%**

- **Korrelation**: Wie stark bewegt sich dieses Symbol *entgegen* deinem Portfolio?
  Berechnet on-the-fly aus historischen Tagesrenditen (kein Caching auf dem Server).
- **RoR%**: Kredit ÷ maximales Risiko der Short-Put-Position

Ein Short Put auf GLD mit Korrelation −0.6 und RoR 12% → Score **7.2**
Ein Short Put auf XLU mit Korrelation −0.3 und RoR 18% → Score **5.4**

→ GLD ist als Crash-Hedge attraktiver, obwohl XLU mehr Prämie bringt.
""")


if __name__ == "__main__":
    main()
