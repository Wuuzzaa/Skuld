"""
Index Short Put — tägliche Arbeitsfläche
=========================================
Kandidaten für den täglichen Index-Short-Put (SPY / XSP als SPX-Proxy).
Zeigt direkt: passende Strikes, Netto-Prämie nach Capture Rate, Teeni-Budget.
"""

import logging
import os

import pandas as pd
import streamlit as st

from src.database import select_into_dataframe

logger = logging.getLogger(os.path.basename(__file__))

# ── Konstanten ────────────────────────────────────────────────────────────────
_INSTRUMENTS = {
    "SPY": {"label": "SPY (S&P 500 ETF)", "multiplier": 100},
    "XSP":  {"label": "XSP (Mini-SPX, 1/10 SPX)", "multiplier": 100},
    "QQQ":  {"label": "QQQ (Nasdaq-100 ETF)", "multiplier": 100},
    "IWM":  {"label": "IWM (Russell 2000 ETF)", "multiplier": 100},
}

# ── Datenladen ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def _load_candidates(symbol: str, dte_min: int, dte_max: int, delta_min: float, delta_max: float) -> pd.DataFrame | None:
    query = """
        SELECT
            symbol,
            strike_price,
            expiration_date,
            days_to_expiration                          AS dte,
            ROUND(day_close::numeric, 2)                AS praemie,
            ROUND(greeks_delta::numeric, 3)             AS delta,
            ROUND(implied_volatility::numeric * 100, 1) AS iv_pct,
            ROUND(iv_rank::numeric, 1)                  AS iv_rank,
            open_interest                               AS oi,
            ROUND(live_stock_price::numeric, 2)         AS underlying_price
        FROM "OptionDataMerged"
        WHERE symbol             = :symbol
          AND contract_type      = 'put'
          AND days_to_expiration BETWEEN :dte_min AND :dte_max
          AND greeks_delta       BETWEEN :delta_min AND :delta_max
          AND day_close          > 0
          AND open_interest      >= 50
        ORDER BY days_to_expiration ASC, ABS(greeks_delta) ASC
    """
    try:
        df = select_into_dataframe(query=query, params={
            "symbol": symbol,
            "dte_min": dte_min,
            "dte_max": dte_max,
            "delta_min": delta_min,
            "delta_max": delta_max,
        })
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.warning(f"Kandidaten-Abfrage fehlgeschlagen: {e}")
        return None


@st.cache_data(ttl=120)
def _load_teeni_candidates(symbol: str) -> pd.DataFrame | None:
    """Weit OTM Puts (Delta ~0.03–0.07) für Tail-Hedge ('Teenis')."""
    query = """
        SELECT
            symbol,
            strike_price,
            expiration_date,
            days_to_expiration                          AS dte,
            ROUND(day_close::numeric, 2)                AS praemie,
            ROUND(greeks_delta::numeric, 3)             AS delta,
            open_interest                               AS oi,
            ROUND(live_stock_price::numeric, 2)         AS underlying_price
        FROM "OptionDataMerged"
        WHERE symbol             = :symbol
          AND contract_type      = 'put'
          AND days_to_expiration BETWEEN 20 AND 60
          AND greeks_delta       BETWEEN -0.08 AND -0.02
          AND day_close          BETWEEN 0.10 AND 1.50
          AND open_interest      >= 20
        ORDER BY days_to_expiration ASC, day_close ASC
        LIMIT 6
    """
    try:
        df = select_into_dataframe(query=query, params={"symbol": symbol})
        return df if df is not None and not df.empty else None
    except Exception as e:
        logger.warning(f"Teeni-Abfrage fehlgeschlagen: {e}")
        return None


# ── Seite ─────────────────────────────────────────────────────────────────────
st.title("📉 Index Short Put")
st.caption("Tägliche Arbeitsfläche: Strike-Auswahl, Netto-Prämie, Teeni-Budget.")

# ── Parameter ─────────────────────────────────────────────────────────────────
col_sym, col_dte, col_delta, col_cr, col_hedge = st.columns([2, 2, 2, 2, 2])

with col_sym:
    st.markdown("**Instrument**")
    symbol = st.radio(
        "Instrument",
        options=list(_INSTRUMENTS.keys()),
        format_func=lambda s: _INSTRUMENTS[s]["label"].split(" ")[0],
        horizontal=True,
        key="isp_symbol",
        label_visibility="collapsed",
    )

with col_dte:
    dte_range = st.slider("DTE-Fenster", min_value=1, max_value=180, value=(75, 105), step=5, key="isp_dte")

with col_delta:
    delta_target = st.slider("Delta-Ziel (Short Put)", min_value=5, max_value=40, value=15, step=1, key="isp_delta")
    delta_band = st.slider("±Band", min_value=1, max_value=10, value=4, step=1, key="isp_delta_band")

with col_cr:
    capture_rate = st.slider("Capture Rate %", min_value=10, max_value=60, value=25, step=5, key="isp_cr",
                             help="Wie viel % der Prämie bleibt nach Stop/TP netto übrig (Castle Trader: 37%, konservativ: 25%)")

with col_hedge:
    hedge_pct = st.slider("Hedge-Budget %", min_value=0, max_value=25, value=10, step=1, key="isp_hedge",
                          help="% des Netto-Gewinns für Tail-Hedges (Teenis)")

delta_min = -(delta_target + delta_band) / 100
delta_max = -(delta_target - delta_band) / 100

multiplier = _INSTRUMENTS[symbol]["multiplier"]

# ── Kandidaten laden ──────────────────────────────────────────────────────────
df = _load_candidates(symbol, dte_range[0], dte_range[1], delta_min, delta_max)

st.divider()

if df is None:
    st.warning(f"Keine Daten für **{symbol}** im gewählten DTE/Delta-Bereich in der DB. "
               f"Prüfe ob {symbol} in den Optionsdaten vorhanden ist.")
    underlying_price = None
else:
    underlying_price = float(df["underlying_price"].iloc[0]) if "underlying_price" in df.columns else None

    # ── Berechnungen ──────────────────────────────────────────────────────────
    df["netto_praemie"] = (df["praemie"] * capture_rate / 100).round(2)
    df["netto_gesamt"]  = (df["netto_praemie"] * multiplier).round(0).astype(int)
    df["hedge_budget"]  = (df["netto_gesamt"] * hedge_pct / 100).round(0).astype(int)
    df["puffer_pct"]    = ((underlying_price - df["strike_price"]) / underlying_price * 100).round(1) if underlying_price else None

    # ── Anzeige ───────────────────────────────────────────────────────────────
    disp = df[[
        "strike_price", "expiration_date", "dte",
        "praemie", "delta", "iv_pct", "iv_rank", "oi",
        "puffer_pct", "netto_praemie", "netto_gesamt", "hedge_budget",
    ]].copy()
    disp.columns = [
        "Strike", "Verfall", "DTE",
        "Prämie $", "Delta", "IV %", "IV Rank", "OI",
        "Puffer %", f"Netto/Aktie @ {capture_rate}%CR", "Netto/Kontrakt $", f"Hedge-Budget $ @ {hedge_pct}%",
    ]

    if underlying_price:
        st.markdown(f"**{symbol}** · Kurs **${underlying_price:,.2f}** · Delta-Ziel **{delta_target}** (±{delta_band}) · DTE **{dte_range[0]}–{dte_range[1]}**")

    def _style_iv(val):
        try:
            v = float(val)
            if v >= 60:
                return "color: #ef4444"
            if v >= 40:
                return "color: #f59e0b"
            return "color: #22c55e"
        except Exception:
            return ""

    sel = st.dataframe(
        disp.style
            .applymap(_style_iv, subset=["IV Rank"])
            .format({
                "Prämie $": "{:.2f}",
                f"Netto/Aktie @ {capture_rate}%CR": "{:.2f}",
                "Delta": "{:.3f}",
            })
            .hide(axis="index"),
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        key="isp_sel",
        height=min(500, 45 + 38 * len(disp)),
    )
    st.caption("🟢 IV Rank < 40 günstig · 🟡 40–60 fair · 🔴 ≥ 60 teuer · Zeile anklicken → Netto als Basis für Teeni-Rechner")

    # Gewählte Zeile → Netto in session state für Teeni-Rechner
    rows_sel = sel.selection.get("rows", []) if sel and sel.selection else []
    if rows_sel:
        selected_netto = int(df["netto_gesamt"].iloc[rows_sel[0]])
        st.session_state["isp_netto_from_sel"] = selected_netto

# ── Teeni-Rechner ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("🛡️ Teeni-Rechner — Tail-Hedge-Budget")

teeni_df = _load_teeni_candidates(symbol)

if "isp_netto_from_sel" in st.session_state:
    netto_default = st.session_state["isp_netto_from_sel"]
elif df is not None and not df.empty:
    netto_default = int(df["netto_gesamt"].median()) if "netto_gesamt" in df.columns else 500
else:
    netto_default = 500

t_col1, t_col2 = st.columns([1, 1])
with t_col1:
    netto_input = st.number_input(
        "Erwarteter Netto-Gewinn pro Trade $",
        min_value=0, value=netto_default, step=50,
        key="isp_netto_input",
        help="Prämie × Capture Rate × Multiplikator — wird aus der Tabelle vorausgefüllt.",
    )
    hedge_budget_dollar = round(netto_input * hedge_pct / 100)
    st.metric(f"Hedge-Budget ({hedge_pct}% von ${netto_input:,})", f"${hedge_budget_dollar:,}")

with t_col2:
    if teeni_df is not None:
        st.markdown(f"**Verfügbare Teenis für {symbol}** (Delta 2–8, Prämie $0.10–$1.50, DTE 20–60):")
        teeni_disp = teeni_df[["strike_price", "expiration_date", "dte", "praemie", "delta", "oi"]].copy()
        teeni_disp.columns = ["Strike", "Verfall", "DTE", "Prämie $", "Delta", "OI"]
        teeni_disp["Stück kaufbar"] = (hedge_budget_dollar / (teeni_disp["Prämie $"] * multiplier)).apply(lambda x: max(0, int(x)))
        teeni_disp["Kosten gesamt $"] = (teeni_disp["Prämie $"] * multiplier * teeni_disp["Stück kaufbar"]).round(0).astype(int)
        st.dataframe(
            teeni_disp.style.hide(axis="index"),
            use_container_width=True,
            height=min(280, 45 + 38 * len(teeni_disp)),
        )
    else:
        st.info(f"Keine Teeni-Kandidaten für {symbol} in DB (Delta 2–8, $0.10–$1.50). "
                "Teenis für SPX/XSP müssten direkt bei CBOE gehandelt werden — Preis manuell eingeben:")
        manual_teeni_px = st.number_input("Teeni-Preis $ (manuell)", min_value=0.01, value=0.30, step=0.05, key="isp_teeni_manual")
        teeni_count = int(hedge_budget_dollar / (manual_teeni_px * multiplier))
        st.metric("Kaufbare Teenis", teeni_count, help=f"Budget ${hedge_budget_dollar} ÷ (${manual_teeni_px} × {multiplier})")

# ── Gedankenstütze ────────────────────────────────────────────────────────────
st.divider()
with st.expander("📋 Regelwerk (Castle Trader)", expanded=False):
    st.markdown("""
| Parameter | Wert |
|---|---|
| Instrument | SPX / XSP (klein) / SPY |
| Richtung | Short Put (naked) |
| DTE | ~90 Tage |
| Delta | ~15 |
| Stop Loss | 200% der Prämie |
| Take Profit | 80% der Prämie |
| Capture Rate (Backtest) | ~37% · konservativ: 25% |
| Hedge-Budget | 10% der Netto-Einnahmen → weit OTM Puts ("Teenis") |
| Frequenz | täglich (oder wöchentlich als Näherung) |

**Teeni = weit OTM Put, Delta ~3–5, Prämie ~$0.25–0.50**
Nicht Delta-neutralisieren, nicht mit Spreads überlagern. Einfach halten.
    """)
