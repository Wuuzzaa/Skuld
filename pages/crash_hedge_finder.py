"""Crash Hedge Finder — Portfolio-Korrelation + Prämienverkauf auf Gegenwerte."""

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

# ── Konstanten ────────────────────────────────────────────────────────────────

# Bekannte Crash-Gegenwerte als Basis-Kandidaten (ergänzen was Korrelation findet)
_KNOWN_HEDGES = ["GLD", "SLV", "TLT", "IEF", "XLU", "XLP", "XLV", "VXX"]

_DTE_MIN_DEFAULT  = 21
_DTE_MAX_DEFAULT  = 60
_LOOKBACK_DEFAULT = 252
_MIN_NEG_CORR     = -0.20   # Schwelle: Korrelation unter diesem Wert gilt als Hedge-Kandidat
_MIN_IV_RANK      = 30.0
_MIN_OI           = 50
_MIN_CREDIT       = 30


# ── CSV-Import (wiederverwendet aus delta_portfolio.py) ───────────────────────

def _parse_ibkr_csv(content: str) -> list[dict]:
    """Parst IBKR/CapTrader Activity Statement CSV → Liste von Positionen."""
    positions = []
    reader = csv.reader(io.StringIO(content))
    mtm_header: list[str] = []

    for row in reader:
        if not row:
            continue
        section = row[0].strip()
        if section != "Mark-to-Market-Performance-Überblick":
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

@st.cache_data(ttl=3600)
def _load_correlations(portfolio_symbols: tuple[str, ...], lookback_days: int) -> pd.DataFrame:
    """
    Lädt vorberechnete Korrelationen aus CorrelationPrecomputed für alle
    Portfolio-Symbole vs. alle bekannten Symbole.
    Gibt DataFrame mit Spalten [peer_symbol, correlation_mean] zurück,
    sortiert aufsteigend (negativste zuerst).
    """
    if not portfolio_symbols:
        return pd.DataFrame()

    df = select_into_dataframe(
        query="""
            SELECT peer_symbol, AVG(correlation) AS correlation_mean
            FROM "CorrelationPrecomputed"
            WHERE base_symbol = ANY(:syms)
              AND lookback_days = :lb
              AND method = 'pearson'
              AND peer_symbol != ALL(:syms)
            GROUP BY peer_symbol
            ORDER BY correlation_mean ASC
        """,
        params={"syms": list(portfolio_symbols), "lb": lookback_days},
    )
    return df if df is not None else pd.DataFrame()


@st.cache_data(ttl=3600)
def _load_portfolio_internal_correlations(symbols: tuple[str, ...], lookback_days: int) -> pd.DataFrame:
    """Korrelationsmatrix der Portfolio-Positionen untereinander."""
    if len(symbols) < 2:
        return pd.DataFrame()
    df = select_into_dataframe(
        query="""
            SELECT base_symbol, peer_symbol, correlation
            FROM "CorrelationPrecomputed"
            WHERE base_symbol = ANY(:syms)
              AND peer_symbol = ANY(:syms)
              AND base_symbol < peer_symbol
              AND lookback_days = :lb
              AND method = 'pearson'
        """,
        params={"syms": list(symbols), "lb": lookback_days},
    )
    return df if df is not None else pd.DataFrame()


@st.cache_data(ttl=600)
def _load_option_candidates(symbols: tuple[str, ...], dte_min: int, dte_max: int,
                             min_oi: int, min_credit: float) -> pd.DataFrame:
    """
    Holt Short-Put- und Bear-Call-Spread-Kandidaten aus OptionDataMerged
    für die gegebenen Symbole (Hedge-Kandidaten).
    """
    if not symbols:
        return pd.DataFrame()

    df = select_into_dataframe(
        query="""
            SELECT
                symbol,
                option_type,
                strike_price,
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
              AND day_close IS NOT NULL
              AND day_close > 0
        """,
        params={"syms": list(symbols), "dte_min": dte_min, "dte_max": dte_max,
                "min_oi": min_oi},
    )
    return df if df is not None else pd.DataFrame()


# ── Strategie-Builder (Short Put) ─────────────────────────────────────────────

def _build_short_put_candidates(opt_df: pd.DataFrame, corr_map: dict,
                                 min_credit: float, min_iv_rank: float) -> list[dict]:
    """
    Baut Short-Put-Kandidaten aus den Optionsdaten.
    Gibt Liste von Dicts zurück, angereichert um correlation und hedge_score.
    """
    results = []
    puts = opt_df[opt_df["option_type"] == "put"].copy()
    for col in ["strike_price", "premium", "greeks_delta", "iv", "iv_rank",
                "open_interest", "dte", "stock_price"]:
        puts[col] = pd.to_numeric(puts[col], errors="coerce")
    puts = puts.dropna(subset=["premium", "greeks_delta", "iv_rank", "stock_price"])

    for (sym, exp), group in puts.groupby(["symbol", "expiration_date"]):
        # Wähle Leg mit Delta ~0.30 (bestes Prämien/Risiko-Verhältnis)
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

        ror = credit / risk * 100
        otm = (stock_price - strike) / stock_price * 100
        corr = corr_map.get(sym, 0.0)
        hedge_score = round(abs(corr) * ror, 2)

        results.append({
            "Strategie":    "Short Put",
            "Symbol":       sym,
            "Verfall":      str(exp),
            "DTE":          dte,
            "Beine":        f"Sell {strike:.2f}P",
            "Kredit $":     round(credit, 0),
            "Max Profit $": round(credit, 0),
            "Max Risiko $": round(risk, 0),
            "RoR %":        round(ror, 1),
            "Breakeven":    round(strike - premium, 2),
            "Delta":        round(float(leg["greeks_delta"]), 2),
            "IV %":         round(iv * 100, 1),
            "IV Rank":      round(iv_rank, 0),
            "OTM %":        round(otm, 1),
            "Korrelation":  round(corr, 3),
            "Hedge Score":  hedge_score,
            "_stock_price": stock_price,
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
        f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'>"
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


def _render_portfolio_heatmap(symbols: list[str], lookback_days: int):
    """Zeigt Korrelations-Heatmap der eigenen Portfolio-Positionen."""
    if len(symbols) < 2:
        st.info("Mindestens 2 Symbole im Portfolio für die Heatmap.")
        return

    corr_df = _load_portfolio_internal_correlations(tuple(sorted(symbols)), lookback_days)
    if corr_df is None or corr_df.empty:
        st.warning("Keine Korrelationsdaten in CorrelationPrecomputed — bitte den Job einmalig auslösen.")
        return

    # Pivot zu quadratischer Matrix
    pairs = corr_df[["base_symbol", "peer_symbol", "correlation"]].copy()
    mirror = pairs.rename(columns={"base_symbol": "peer_symbol", "peer_symbol": "base_symbol"})
    full = pd.concat([pairs, mirror], ignore_index=True)
    diag = pd.DataFrame([{"base_symbol": s, "peer_symbol": s, "correlation": 1.0} for s in symbols])
    full = pd.concat([full, diag], ignore_index=True)
    matrix = full.pivot(index="base_symbol", columns="peer_symbol", values="correlation")
    matrix = matrix.reindex(index=sorted(symbols), columns=sorted(symbols))

    # Färbung: grün=negativ (gut für Diversifikation), rot=positiv (Klumpenrisiko)
    styled = (
        matrix.style
        .background_gradient(cmap="RdYlGn_r", vmin=-1, vmax=1)
        .format("{:.2f}")
    )
    st.dataframe(styled, use_container_width=True)

    # Warnung bei hoher interner Korrelation
    high_corr_pairs = [(r["base_symbol"], r["peer_symbol"])
                       for _, r in pairs.iterrows() if r["correlation"] >= 0.7]
    if high_corr_pairs:
        pair_strs = ", ".join(f"{a}/{b}" for a, b in high_corr_pairs[:5])
        st.warning(f"Klumpenrisiko: {pair_strs} korrelieren ≥ 0.70 — ein Crash trifft alle gleichzeitig.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("Crash Hedge Finder")
    st.caption(
        "Importiere dein Portfolio → sieh welche Symbole negativ korreliert sind "
        "→ finde Optionsstrategien auf diese Gegenwerte, die gleichzeitig Prämie bringen."
    )

    # ── Portfolio laden ───────────────────────────────────────────────────────
    st.subheader("1. Portfolio eingeben")
    col_csv, col_manual = st.columns([1, 1])

    with col_csv:
        st.markdown("**CSV-Import (CapTrader / IBKR)**")
        uploaded = st.file_uploader("Activity Statement CSV hochladen", type=["csv"], key="chf_csv")
        if uploaded is not None:
            content = uploaded.read().decode("utf-8", errors="replace")
            imported = _parse_ibkr_csv(content)
            if imported:
                st.session_state["chf_positions"] = imported
                st.success(f"{len(imported)} Positionen importiert.")
            else:
                st.error("Keine Positionen gefunden — prüfe ob die CSV die 'Mark-to-Market-Performance-Überblick' Sektion enthält.")

    with col_manual:
        st.markdown("**Oder Symbole manuell eingeben**")
        manual_input = st.text_input(
            "Symbole (kommagetrennt)", placeholder="AAPL, MSFT, NVDA, AMZN",
            key="chf_manual"
        )
        if st.button("Symbole übernehmen", key="chf_manual_btn") and manual_input:
            syms = [s.strip().upper() for s in manual_input.split(",") if s.strip()]
            st.session_state["chf_positions"] = [{"type": "stock", "symbol": s, "qty": 100, "direction": "Long"} for s in syms]
            st.success(f"{len(syms)} Symbole übernommen.")

    positions: list[dict] = st.session_state.get("chf_positions", [])
    if not positions:
        st.info("Portfolio hochladen oder Symbole eingeben um fortzufahren.")
        return

    # Nur Long-Positionen als Hedge-Basis (Short-Positionen hedgen sich selbst)
    portfolio_symbols = sorted({
        p["symbol"] for p in positions
        if p.get("direction", "Long") == "Long"
    })
    st.success(f"Portfolio: **{', '.join(portfolio_symbols)}** ({len(portfolio_symbols)} Symbole)")

    # ── Parameter ─────────────────────────────────────────────────────────────
    with st.expander("Parameter", expanded=True):
        p1, p2, p3 = st.columns(3)
        with p1:
            lookback_days = st.selectbox(
                "Korrelations-Lookback", [63, 126, 252, 504],
                index=2,
                format_func=lambda x: {63: "3 Monate", 126: "6 Monate",
                                        252: "1 Jahr", 504: "2 Jahre"}[x],
            )
            min_neg_corr = st.slider(
                "Max. Korrelation (Schwelle)", -1.0, 0.0, _MIN_NEG_CORR, 0.05,
                help="Nur Symbole zeigen, die zu deinem Portfolio maximal diese Korrelation haben."
            )
        with p2:
            dte_range = st.slider("DTE-Fenster", 7, 120, (_DTE_MIN_DEFAULT, _DTE_MAX_DEFAULT))
            min_iv_rank = st.slider("Min. IV Rank", 0, 100, int(_MIN_IV_RANK), 5)
        with p3:
            min_credit = st.number_input("Min. Kredit ($)", 0, 5000, _MIN_CREDIT, 10)
            min_oi = st.number_input("Min. Open Interest", 0, 10000, _MIN_OI, 10)
            top_n = st.slider("Top N Gegenwerte", 5, 50, 20, 5,
                               help="Wie viele negativ-korrelierte Symbole maximal berücksichtigen.")

    run = st.button("Hedge-Kandidaten suchen", type="primary", use_container_width=True)

    if not run and "chf_results" not in st.session_state:
        # Heatmap trotzdem zeigen wenn Daten vorhanden
        if len(portfolio_symbols) >= 2:
            st.subheader("Portfolio-Korrelationsmatrix")
            _render_portfolio_heatmap(portfolio_symbols, lookback_days)
        return

    if run:
        # ── Schritt 1: Portfolio-interne Korrelation ──────────────────────────
        # ── Schritt 2: Negativ-korrelierte Gegenwerte laden ───────────────────
        with st.spinner("Lade Korrelationsdaten..."):
            corr_df = _load_correlations(tuple(portfolio_symbols), lookback_days)

        if corr_df is None or corr_df.empty:
            st.error(
                "Keine Daten in `CorrelationPrecomputed` — der Job muss einmalig ausgeführt werden. "
                "Im Admin-Bereich unter **Jobs** den Modus `correlation_precompute` starten."
            )
            return

        # Filtere auf negativ korrelierte Kandidaten
        neg_corr = corr_df[corr_df["correlation_mean"] <= min_neg_corr].head(top_n)

        # Bekannte Crash-Gegenwerte immer ergänzen (falls vorhanden in DB)
        extra_hedges = [s for s in _KNOWN_HEDGES if s not in neg_corr["peer_symbol"].values]
        if extra_hedges:
            extra_df = corr_df[corr_df["peer_symbol"].isin(extra_hedges)]
            neg_corr = pd.concat([neg_corr, extra_df], ignore_index=True).drop_duplicates("peer_symbol")

        if neg_corr.empty:
            st.warning("Keine negativ-korrelierten Symbole gefunden. Schwelle erhöhen oder Lookback ändern.")
            return

        corr_map = dict(zip(neg_corr["peer_symbol"], neg_corr["correlation_mean"]))
        candidate_symbols = tuple(neg_corr["peer_symbol"].tolist())

        # ── Schritt 3: Optionskandidaten laden ───────────────────────────────
        with st.spinner(f"Lade Optionsdaten für {len(candidate_symbols)} Gegenwerte..."):
            opt_df = _load_option_candidates(
                candidate_symbols, dte_range[0], dte_range[1], min_oi, min_credit
            )

        if opt_df is None or opt_df.empty:
            st.warning("Keine Optionsdaten gefunden. DTE-Fenster oder OI-Filter anpassen.")
            return

        # ── Schritt 4: Strategie bauen ────────────────────────────────────────
        results = _build_short_put_candidates(opt_df, corr_map, min_credit, min_iv_rank)
        results.sort(key=lambda x: x["Hedge Score"], reverse=True)

        st.session_state["chf_results"]   = results
        st.session_state["chf_corr_df"]   = neg_corr
        st.session_state["chf_portfolio"] = portfolio_symbols
        st.session_state["chf_lookback"]  = lookback_days

    # ── Ergebnisse anzeigen ───────────────────────────────────────────────────
    results       = st.session_state.get("chf_results", [])
    neg_corr      = st.session_state.get("chf_corr_df", pd.DataFrame())
    portfolio_syms = st.session_state.get("chf_portfolio", portfolio_symbols)
    lb            = st.session_state.get("chf_lookback", lookback_days)

    tab_heatmap, tab_corr, tab_strategies = st.tabs([
        "Portfolio-Matrix", "Negativ-Korrelierte", "Hedge-Strategien"
    ])

    with tab_heatmap:
        st.markdown("#### Korrelation deiner Portfolio-Positionen untereinander")
        st.caption("Rot = hohe positive Korrelation (Klumpenrisiko) · Grün = niedrig/negativ (gut diversifiziert)")
        _render_portfolio_heatmap(tuple(portfolio_syms), lb)

    with tab_corr:
        st.markdown("#### Gefundene Gegenwerte — negativ zum Portfolio korreliert")
        if not neg_corr.empty:
            styled_corr = (
                neg_corr.rename(columns={"peer_symbol": "Symbol", "correlation_mean": "Korrelation (Ø)"})
                .style
                .background_gradient(subset=["Korrelation (Ø)"], cmap="RdYlGn", vmin=-1, vmax=0)
                .format({"Korrelation (Ø)": "{:.3f}"})
            )
            st.dataframe(styled_corr, hide_index=True, use_container_width=True)
            st.caption(
                "Korrelation < −0.4: starke Gegenbewegung bei Crash (grün) · "
                "−0.4 bis −0.2: moderate Absicherung (gelb)"
            )

    with tab_strategies:
        if not results:
            st.info("Keine Strategien gefunden — Parameter lockern.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Kandidaten", len({r["Symbol"] for r in results}))
            m2.metric("Strategien", len(results))
            top = results[0]
            m3.metric("Bester Hedge Score", f"{top['Hedge Score']:.2f}")
            m4.metric("Bester RoR", f"{top['RoR %']:.1f}%")

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
                    "**Hedge Score** = |Korrelation| × RoR% — je höher, desto besser als Crash-Hedge mit Prämie."
                )

            with st.expander("Wie funktioniert der Hedge Score?"):
                st.markdown("""
**Hedge Score = |Korrelation| × RoR%**

- **Korrelation** (aus `CorrelationPrecomputed`): Wie stark bewegt sich dieses Symbol *entgegen* deinem Portfolio?
  - −1.0 = perfekte Gegenbewegung · 0.0 = keine Verbindung · +1.0 = gleiche Richtung
- **RoR%** (Return on Risk): Kredit geteilt durch maximales Risiko der Option

Ein Short Put auf GLD mit Korrelation −0.6 und RoR 12% ergibt Score 7.2.
Ein Short Put auf XLU mit Korrelation −0.3 und RoR 18% ergibt Score 5.4.
→ GLD ist als Crash-Hedge attraktiver, obwohl XLU mehr Prämie bringt.

**Tipp:** Prüfe auch die Earnings-Warnung und den IV Rank vor dem Einstieg.
""")


if __name__ == "__main__":
    main()
