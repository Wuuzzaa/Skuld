"""
Portfolio Hedge Calculator
==========================
Portfolio hochladen → aktuelle Prämieneinnahmen + Absicherungskosten vollautomatisch aus DB.
"""

import csv
import io
import logging
import os
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.database import select_into_dataframe

logger = logging.getLogger(os.path.basename(__file__))

# ── Beta-Tabelle (Fallback wenn nicht in DB) ──────────────────────────────────
_BETA_MAP = {
    "META": 1.25, "GOOGL": 1.15, "GOOG": 1.15, "AMZN": 1.20, "NVDA": 1.60,
    "MSFT": 1.10, "AAPL": 1.10, "TSLA": 1.80, "CRM": 1.30, "PLTR": 1.70,
    "INTC": 1.20, "ORCL": 1.10, "WDAY": 1.35, "BE": 1.50, "SMCI": 1.90,
    "WMT": 0.55, "MRK": 0.75, "GILD": 0.75, "DHR": 1.00, "ZTS": 0.90,
    "BA": 1.35, "DAL": 1.40, "VLO": 1.10, "OKE": 0.85,
    "ISRG": 1.05, "UBER": 1.45, "CF": 1.10,
}
_DEFAULT_BETA = 1.0

_SCENARIOS = [
    ("-5% Rücksetzer",   -0.05),
    ("-10% Korrektur",   -0.10),
    ("-20% Bärenmarkt",  -0.20),
    ("-35% Crash",       -0.35),
    ("-50% Krise",       -0.50),
]

# VIX steigt historisch bei Markteinbrüchen (Faustregel aus 2008/2020/2022)
_VIX_AT_DROP = {
    -0.05: 1.5, -0.10: 2.0, -0.20: 3.0, -0.35: 5.0, -0.50: 8.0
}


# ── CSV-Parser ────────────────────────────────────────────────────────────────

def _extract_symbol(raw: str) -> str | None:
    raw = raw.strip()
    m = re.match(r"^([A-Z0-9]{1,6})\s+\d{6}[CP]\d+", raw)
    if m:
        return m.group(1)
    if re.match(r"^[A-Z]{1,5}$", raw):
        return raw
    return None


def _parse_position_report(content: str) -> list[dict]:
    positions = []
    reader = csv.reader(io.StringIO(content))
    header = []
    for row in reader:
        if not row:
            continue
        if not header:
            header = [c.strip().strip('"') for c in row]
            continue
        data = dict(zip(header, [c.strip().strip('"') for c in row]))
        asset_class = data.get("AssetClass", "").strip()
        symbol_raw = data.get("Symbol", "").strip()
        try:
            qty = float(data.get("Quantity", "0") or "0")
        except ValueError:
            continue
        if qty == 0:
            continue
        try:
            mark = float(data.get("MarkPrice", "0") or "0")
        except ValueError:
            mark = 0.0
        try:
            strike = float(data.get("Strike", "0") or "0")
        except ValueError:
            strike = 0.0

        if asset_class == "STK":
            positions.append({"type": "stock", "symbol": symbol_raw,
                               "qty": qty, "mark": mark, "strike": 0.0,
                               "direction": "Long" if qty > 0 else "Short"})
        elif asset_class == "OPT":
            underlying = _extract_symbol(symbol_raw)
            if underlying:
                positions.append({"type": "option", "symbol": underlying,
                                   "qty": qty, "mark": mark, "strike": strike,
                                   "direction": "Long" if qty > 0 else "Short"})
    return positions


def _parse_trades_report(content: str) -> list[dict]:
    """Trades_Report Format: nettiert nach Symbol+Strike+Expiry — offene Positionen."""
    from collections import defaultdict
    try:
        reader = csv.DictReader(io.StringIO(content))
        trades = list(reader)
    except Exception:
        return []
    net: dict = defaultdict(float)
    info: dict = {}
    for t in trades:
        sym = t.get('Symbol', '').strip().split()[0]
        key = (sym, t.get('Strike', ''), t.get('Expiry', ''), t.get('Put/Call', ''))
        try:
            qty = float(t.get('Quantity', 0))
        except ValueError:
            qty = 0
        net[key] += qty
        info[key] = t
    positions = []
    for key, qty in net.items():
        if abs(qty) < 0.5:
            continue
        sym, strike, expiry, pc = key
        t = info[key]
        try:
            mark = float(t.get('TradePrice', 0))
        except ValueError:
            mark = 0.0
        try:
            strike_f = float(strike) if strike else 0.0
        except ValueError:
            strike_f = 0.0
        positions.append({
            "type": "option", "symbol": sym, "qty": qty,
            "mark": mark, "strike": strike_f,
            "direction": "Long" if qty > 0 else "Short",
            "put_call": pc,
        })
    return positions


def _parse_csv(content: str) -> list[dict]:
    first = content.lstrip()
    if first.startswith('"ClientAccountID"') or first.startswith('ClientAccountID'):
        first_line = content.split('\n')[0]
        if 'Open/CloseIndicator' in first_line or 'FifoPnlRealized' in first_line:
            return _parse_trades_report(content)
        return _parse_position_report(content)
    return []


# ── DB-Abfragen ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def _fetch_spy_price() -> float:
    try:
        df = select_into_dataframe(
            'SELECT close FROM "StockPricesYahoo" WHERE symbol = :sym ORDER BY date DESC LIMIT 1',
            params={"sym": "SPY"}
        )
        if df is not None and not df.empty:
            return float(df.iloc[0, 0])
    except Exception:
        pass
    return 560.0


@st.cache_data(ttl=300)
def _fetch_qqq_price() -> float:
    try:
        df = select_into_dataframe(
            'SELECT close FROM "StockPricesYahoo" WHERE symbol = :sym ORDER BY date DESC LIMIT 1',
            params={"sym": "QQQ"}
        )
        if df is not None and not df.empty:
            return float(df.iloc[0, 0])
    except Exception:
        pass
    return 480.0


@st.cache_data(ttl=300)
def _fetch_vix() -> float:
    try:
        df = select_into_dataframe(
            'SELECT close FROM "StockPricesYahoo" WHERE symbol = :sym ORDER BY date DESC LIMIT 1',
            params={"sym": "^VIX"}
        )
        if df is not None and not df.empty:
            return float(df.iloc[0, 0])
    except Exception:
        pass
    return 18.0


@st.cache_data(ttl=300)
def _fetch_put_spreads(symbol: str, dte_min: int, dte_max: int) -> pd.DataFrame:
    """Holt Short-Put-Kandidaten aus OptionDataMerged für Hedge-Instrument."""
    try:
        df = select_into_dataframe(
            """
            SELECT
                strike_price,
                day_close          AS premium,
                days_to_expiration AS dte,
                expiration_date,
                live_stock_price   AS stock_price,
                abs(greeks_delta)  AS delta,
                implied_volatility AS iv,
                open_interest      AS oi
            FROM "OptionDataMerged"
            WHERE symbol           = :sym
              AND contract_type    = 'put'
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND day_close        > 0
              AND open_interest    >= 100
            ORDER BY expiration_date ASC, strike_price DESC
            """,
            params={"sym": symbol, "dte_min": dte_min, "dte_max": dte_max}
        )
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"put_spreads query failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def _fetch_current_premiums(symbols: list[str], dte_min: int, dte_max: int) -> pd.DataFrame:
    """Holt aktuelle Short-Put-Prämien für Portfolio-Symbole aus DB."""
    if not symbols:
        return pd.DataFrame()
    try:
        df = select_into_dataframe(
            """
            SELECT
                symbol,
                strike_price,
                day_close           AS premium,
                days_to_expiration  AS dte,
                abs(greeks_delta)   AS delta,
                open_interest       AS oi,
                iv_rank,
                live_stock_price    AS stock_price,
                expiration_date
            FROM "OptionDataMerged"
            WHERE symbol           = ANY(:syms)
              AND contract_type    = 'put'
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND abs(greeks_delta) BETWEEN 0.20 AND 0.40
              AND day_close        > 0
              AND open_interest    >= 50
            ORDER BY symbol, abs(greeks_delta - 0.30)
            """,
            params={"syms": symbols, "dte_min": dte_min, "dte_max": dte_max}
        )
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"current_premiums query failed: {e}")
        return pd.DataFrame()


# ── Berechnungslogik ──────────────────────────────────────────────────────────

def _beta(symbol: str) -> float:
    return _BETA_MAP.get(symbol, _DEFAULT_BETA)


def _portfolio_metrics(positions: list[dict]) -> dict:
    """
    Berechnet aus den Portfolio-Positionen:
    - Max-Loss-Notional aller Short Puts (Strike × 100 × Qty)
    - Beta-gewichtetes Notional
    - Liste der Short-Put-Symbole für DB-Abfragen
    """
    rows = []
    total_notional = 0.0
    total_beta_notional = 0.0
    short_put_symbols = []

    for p in positions:
        if p.get("direction") != "Short":
            continue
        sym = p["symbol"]
        strike = p.get("strike", 0.0)
        qty = abs(p.get("qty", 1))
        if strike == 0:
            continue
        notional = strike * 100 * qty
        b = _beta(sym)
        beta_notional = notional * b
        total_notional += notional
        total_beta_notional += beta_notional
        short_put_symbols.append(sym)
        rows.append({
            "Symbol": sym, "Kontrakte": int(qty),
            "Strike": strike, "Notional $": notional,
            "Beta": b, "Beta-Notional $": beta_notional,
        })

    return {
        "rows": rows,
        "total_notional": total_notional,
        "beta_notional": total_beta_notional,
        "symbols": list(set(short_put_symbols)),
    }


def _estimated_portfolio_loss(beta_notional: float, drop: float) -> float:
    """Verlust eines Short-Put-Portfolios bei Markteinbruch.
    Gamma/Vega-Multiplikator: bei tiefem Crash steigen implizite Verluste überproportional."""
    gamma_factor = 1.0 + abs(drop) * 0.8
    return beta_notional * abs(drop) * gamma_factor


def _spy_put_spread_cost(df_puts: pd.DataFrame, spy_price: float,
                          hedge_pct: float, beta_notional: float,
                          target_drop: float = -0.10) -> dict | None:
    """
    Sucht automatisch passenden Put Spread aus DB-Daten.
    Short Put: ~5-8% OTM (Strike ≈ spy_price × 0.93)
    Long Put:  ~12-15% OTM (Strike ≈ spy_price × 0.87)
    """
    if df_puts.empty:
        return None

    short_target = spy_price * (1 + target_drop * 0.5)   # Short Leg: halber Weg
    long_target  = spy_price * (1 + target_drop)          # Long Leg: voller Drop

    df = df_puts.copy()
    df["dist_short"] = abs(df["strike_price"] - short_target)
    df["dist_long"]  = abs(df["strike_price"] - long_target)

    row_short = df.nsmallest(1, "dist_short").iloc[0] if not df.empty else None
    row_long  = df.nsmallest(1, "dist_long").iloc[0]  if not df.empty else None

    if row_short is None or row_long is None:
        return None
    if row_short["strike_price"] <= row_long["strike_price"]:
        return None

    short_premium = float(row_short["premium"])
    long_premium  = float(row_long["premium"])
    net_debit     = long_premium - short_premium
    if net_debit <= 0:
        net_debit = long_premium * 0.3  # Mindest-Debit

    protected_notional = beta_notional * hedge_pct
    n_contracts = max(1, round(protected_notional / (spy_price * 100)))
    total_cost  = net_debit * 100 * n_contracts
    width       = row_short["strike_price"] - row_long["strike_price"]
    max_payout  = width * 100 * n_contracts

    return {
        "short_strike": row_short["strike_price"],
        "short_premium": short_premium,
        "long_strike":  row_long["strike_price"],
        "long_premium": long_premium,
        "net_debit": net_debit,
        "n_contracts": n_contracts,
        "total_cost": total_cost,
        "max_payout": max_payout,
        "width": width,
        "dte": int(row_short["dte"]),
        "expiry": str(row_short["expiration_date"]),
    }


# ── Charts ────────────────────────────────────────────────────────────────────

def _chart_scenario(beta_notional: float, hedge_cost: float, hedge_pct: float,
                    annual_income: float) -> go.Figure:
    labels = [s[0] for s in _SCENARIOS]
    drops  = [s[1] for s in _SCENARIOS]
    losses_raw    = [_estimated_portfolio_loss(beta_notional, d) for d in drops]
    losses_hedged = [max(0, l - l * hedge_pct * 0.8) for l in losses_raw]

    fig = go.Figure()
    fig.add_bar(name="Verlust ungesichert", x=labels, y=losses_raw,
                marker_color="#ef4444", opacity=0.85)
    fig.add_bar(name="Verlust nach Hedge",  x=labels, y=losses_hedged,
                marker_color="#f97316", opacity=0.85)
    fig.add_hline(y=annual_income / 12, line_dash="dot", line_color="#22c55e",
                  annotation_text="1 Monat Prämie")
    fig.add_hline(y=annual_income, line_dash="dot", line_color="#3b82f6",
                  annotation_text="12 Monate Prämie")
    fig.update_layout(
        title="Verlust-Szenarien: Ungesichert vs. Gesichert",
        barmode="group", yaxis_title="Verlust ($)",
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font_color="#e5e7eb", height=380,
        legend=dict(orientation="h", y=1.05),
    )
    return fig


def _chart_cost_vs_income(monthly_income: float, hedge_options: list[dict]) -> go.Figure:
    labels = [h["label"] for h in hedge_options]
    annual_costs = [h["annual_cost"] for h in hedge_options]
    annual_income = monthly_income * 12

    fig = go.Figure()
    fig.add_bar(x=labels, y=annual_costs, name="Jährl. Hedge-Kosten",
                marker_color="#8b5cf6")
    fig.add_hline(y=annual_income, line_dash="dot", line_color="#22c55e",
                  annotation_text=f"Jahresprämie ${annual_income:,.0f}")
    fig.add_hline(y=annual_income * 0.20, line_dash="dash", line_color="#eab308",
                  annotation_text="20%-Grenze (Ziel)")
    fig.update_layout(
        title="Hedge-Kosten vs. Jahresprämie",
        yaxis_title="$ / Jahr",
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font_color="#e5e7eb", height=330,
    )
    return fig


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.header("Portfolio Hedge Calculator")
    st.caption("Portfolio hochladen → Prämieneinnahmen + Absicherungskosten automatisch aus DB.")

    # ── Portfolio laden ───────────────────────────────────────────────────────
    col_up, col_opt = st.columns([2, 1])
    with col_up:
        uploaded = st.file_uploader("IBKR/CapTrader CSV", type=["csv"],
                                    help="Flex Query Position Report oder Trades_Report CSV")
    with col_opt:
        manual = st.text_area("Oder Symbole (kommagetrennt)", placeholder="META, GOOGL, BA ...",
                              height=68)

    positions: list[dict] = []
    if uploaded:
        try:
            content = uploaded.read().decode("utf-8", errors="ignore")
            positions = _parse_csv(content)
            if positions:
                st.success(f"{len(positions)} Positionen geladen")
            else:
                st.warning("Format nicht erkannt — bitte Flex Query Position Report oder Trades_Report verwenden.")
        except Exception as e:
            st.error(f"Fehler: {e}")
    elif manual.strip():
        for sym in [s.strip().upper() for s in manual.split(",") if s.strip()]:
            positions.append({"type": "option", "symbol": sym, "qty": -1,
                               "mark": 2.0, "strike": 100.0, "direction": "Short"})

    if not positions:
        st.info("Bitte CSV hochladen oder Symbole eingeben.")
        return

    # ── Parameter ─────────────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        hedge_pct = st.slider("Absicherungsgrad", 10, 100, 50, 5, format="%d%%") / 100
    with c2:
        dte_hedge = st.select_slider("Laufzeit Hedge (DTE)", [21, 30, 45, 60, 90], value=30)
    with c3:
        hedge_instrument = st.selectbox("Hedge-Instrument", ["SPY", "QQQ"])

    # ── Marktdaten aus DB ─────────────────────────────────────────────────────
    spy_price = _fetch_spy_price()
    qqq_price = _fetch_qqq_price()
    vix       = _fetch_vix()
    instr_price = spy_price if hedge_instrument == "SPY" else qqq_price

    m1, m2, m3 = st.columns(3)
    m1.metric("SPY", f"${spy_price:.2f}")
    m2.metric("QQQ", f"${qqq_price:.2f}")
    m3.metric("VIX", f"{vix:.1f}")

    # ── Portfolio-Metriken ────────────────────────────────────────────────────
    metrics = _portfolio_metrics(positions)
    beta_notional  = metrics["beta_notional"]
    total_notional = metrics["total_notional"]
    symbols        = metrics["symbols"]

    if beta_notional == 0:
        st.warning("Keine Short-Put-Positionen mit Strike erkannt. Bitte Position Report mit Strike-Daten hochladen.")
        st.info("Tipp: Flex Query Position Report enthält Strikes. Der Trades_Report enthält Strikes wenn offene Positionen vorhanden sind.")
        return

    # Prämieneinnahmen aus DB für alle Portfolio-Symbole
    df_prems = _fetch_current_premiums(symbols, dte_min=21, dte_max=dte_hedge + 15)

    if not df_prems.empty:
        # Beste Option pro Symbol (Delta ~0.30)
        df_best = df_prems.sort_values("delta").groupby("symbol").first().reset_index()
        monthly_income_db = (df_best["premium"] * 100).sum()
    else:
        monthly_income_db = 0.0

    monthly_income = monthly_income_db if monthly_income_db > 0 else total_notional * 0.005
    annual_income  = monthly_income * 12

    # ── Kennzahlen-Banner ─────────────────────────────────────────────────────
    st.divider()
    ka, kb, kc, kd = st.columns(4)
    ka.metric("Max-Loss Notional",       f"${total_notional:,.0f}",
              help="Strike × 100 × Qty — Worst Case wenn alle Puts ITM")
    kb.metric("Beta-gewichtetes Notional", f"${beta_notional:,.0f}",
              help="SPY-Äquivalent: wie viel SPY-Risiko du trägst")
    kc.metric("Monatl. Prämie (DB)",     f"${monthly_income:,.0f}",
              help="Aktuelle Prämien Delta ~0.30, deiner DTE aus OptionDataMerged")
    kd.metric("Jahresprämie (Schätzung)", f"${annual_income:,.0f}")

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📉 Szenario-Analyse",
        "🛡️ Put Spread Hedge",
        "⚡ VIX-basierter Hedge",
        "📊 Vergleich Hedge-Optionen",
    ])

    # ── Tab 1: Szenario-Analyse ───────────────────────────────────────────────
    with tab1:
        rows = []
        for label, drop in _SCENARIOS:
            loss = _estimated_portfolio_loss(beta_notional, drop)
            protected = loss * hedge_pct * 0.8
            net_loss  = loss - protected
            months_raw    = loss / monthly_income if monthly_income else 0
            months_hedged = net_loss / monthly_income if monthly_income else 0
            rows.append({
                "Szenario":                    label,
                "Markt":                       f"{drop*100:.0f}%",
                "Verlust ungesichert":         f"${loss:,.0f}",
                "Verlust gesichert":           f"${net_loss:,.0f}",
                "Schutz":                      f"${protected:,.0f}",
                "Erholung ungesichert (Monate)": f"{months_raw:.1f}",
                "Erholung gesichert (Monate)":   f"{months_hedged:.1f}",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.plotly_chart(_chart_scenario(beta_notional, 0, hedge_pct, annual_income),
                        use_container_width=True)

        if metrics["rows"]:
            with st.expander("Beta-Gewichtung der Positionen"):
                df_bw = pd.DataFrame(metrics["rows"])
                df_bw["Notional $"]      = df_bw["Notional $"].apply(lambda x: f"${x:,.0f}")
                df_bw["Beta-Notional $"] = df_bw["Beta-Notional $"].apply(lambda x: f"${x:,.0f}")
                st.dataframe(df_bw, use_container_width=True, hide_index=True)

    # ── Tab 2: Put Spread Hedge ───────────────────────────────────────────────
    with tab2:
        st.markdown(f"**{hedge_instrument} Put Spread — automatisch aus DB berechnet ({dte_hedge} DTE)**")

        df_puts = _fetch_put_spreads(hedge_instrument, dte_min=dte_hedge - 10, dte_max=dte_hedge + 10)
        spread = _spy_put_spread_cost(df_puts, instr_price, hedge_pct, beta_notional)

        if spread:
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Short Put Strike",  f"${spread['short_strike']:.0f}",
                      delta=f"Prämie ${spread['short_premium']:.2f}")
            s2.metric("Long Put Strike",   f"${spread['long_strike']:.0f}",
                      delta=f"Prämie ${spread['long_premium']:.2f}")
            s3.metric("Netto-Debit / Kontrakt", f"${spread['net_debit']*100:.0f}")
            s4.metric("Benötigte Kontrakte",    spread["n_contracts"])

            total_cost   = spread["total_cost"]
            annual_cost  = total_cost * (365 / spread["dte"])
            cost_pct     = annual_cost / annual_income * 100 if annual_income else 0
            max_payout   = spread["max_payout"]

            st.markdown("---")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Gesamtkosten Hedge",   f"${total_cost:,.0f}")
            c2.metric("Annualisiert",          f"${annual_cost:,.0f}")
            c3.metric("% der Jahresprämie",    f"{cost_pct:.1f}%",
                      delta_color="inverse")
            c4.metric("Max. Auszahlung",       f"${max_payout:,.0f}")

            if cost_pct < 10:
                st.success(f"✅ Sehr effizient: {cost_pct:.1f}% der Jahresprämie.")
            elif cost_pct < 20:
                st.info(f"ℹ️ Akzeptabel: {cost_pct:.1f}% der Jahresprämie.")
            elif cost_pct < 40:
                st.warning(f"⚠️ Teuer: {cost_pct:.1f}% — VIX aktuell {vix:.0f}, hohe IV erhöht Kosten.")
            else:
                st.error(f"🚨 Unwirtschaftlich: {cost_pct:.1f}% — Prämieneinnahmen werden stark belastet.")

            # Break-Even pro Szenario
            st.markdown("**Break-Even: Wann lohnt sich der Hedge?**")
            be_rows = []
            for label, drop in _SCENARIOS:
                port_loss   = _estimated_portfolio_loss(beta_notional, drop)
                payout_est  = min(max_payout, port_loss * hedge_pct)
                net_benefit = payout_est - total_cost
                be_rows.append({
                    "Szenario":          label,
                    "Portfolio-Verlust": f"${port_loss:,.0f}",
                    "Hedge-Auszahlung":  f"${payout_est:,.0f}",
                    "Hedge-Kosten":      f"${total_cost:,.0f}",
                    "Netto-Vorteil":     f"${net_benefit:,.0f}",
                    "Lohnt sich":        "✅" if net_benefit > 0 else "❌",
                })
            st.dataframe(pd.DataFrame(be_rows), use_container_width=True, hide_index=True)

            # Sensitivität: verschiedene Absicherungsgrade
            st.markdown("**Sensitivität: Absicherungsgrad**")
            sens_rows = []
            for pct in [0.25, 0.50, 0.75, 1.0]:
                n = max(1, round(beta_notional * pct / (instr_price * 100)))
                cost = spread["net_debit"] * 100 * n
                ann  = cost * (365 / spread["dte"])
                sens_rows.append({
                    "Absicherung":       f"{pct*100:.0f}%",
                    "Kontrakte":         n,
                    "Kosten pro Periode": f"${cost:,.0f}",
                    "Annualisiert":      f"${ann:,.0f}",
                    "% Jahresprämie":    f"{ann/annual_income*100:.1f}%" if annual_income else "–",
                })
            st.dataframe(pd.DataFrame(sens_rows), use_container_width=True, hide_index=True)

            # Rohdaten der Put-Kette
            if not df_puts.empty:
                with st.expander(f"{hedge_instrument} Put-Kette ({dte_hedge} DTE)"):
                    df_show = df_puts[["strike_price","premium","delta","iv","oi","dte","expiration_date"]].copy()
                    df_show.columns = ["Strike","Prämie","Delta","IV","OI","DTE","Expiry"]
                    st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.warning(
                f"Keine {hedge_instrument}-Put-Daten für DTE {dte_hedge} in DB gefunden. "
                "Bitte DTE anpassen oder DB-Update abwarten."
            )

        if not df_prems.empty:
            with st.expander("Aktuelle Portfolio-Prämien aus DB"):
                df_show = df_prems[["symbol","strike_price","premium","delta","iv_rank","oi","dte"]].copy()
                df_show.columns = ["Symbol","Strike","Prämie","Delta","IV Rank","OI","DTE"]
                st.dataframe(df_show, use_container_width=True, hide_index=True)

    # ── Tab 3: VIX-basierter Hedge ────────────────────────────────────────────
    with tab3:
        st.markdown("**VIX Call als Crash-Versicherung**")
        st.caption(
            f"VIX aktuell: {vix:.1f}. VIX-Optionen sind nicht im DB-Feed — "
            "Preise werden basierend auf VIX-Niveau und Laufzeit geschätzt."
        )

        # VIX Call Preis-Schätzung (Black-Scholes-Näherung nicht verfügbar ohne Optionsdaten)
        # Faustregel: OTM VIX Call bei 1.5× Strike kostet ~1-3% des Strikes
        vix_strike_default = round(vix * 1.5)
        vix_call_est = vix * 0.08  # ~8% des VIX-Niveaus als Call-Prämie (grobe Schätzung)

        vc1, vc2, vc3 = st.columns(3)
        vix_strike   = vc1.number_input("VIX Call Strike", min_value=15.0,
                                         value=float(vix_strike_default), step=1.0)
        vix_call_prc = vc2.number_input("VIX Call Preis ($)", min_value=0.1,
                                         value=round(vix_call_est, 2), step=0.1,
                                         help="Manuell eingeben — aus thinkorswim oder IBKR Option Chain")
        n_vix = vc3.number_input("Anzahl Kontrakte", min_value=1, value=max(1, int(beta_notional / 50000)), step=1)

        total_vix_cost = vix_call_prc * 100 * n_vix
        annual_vix     = total_vix_cost * 12 if dte_hedge <= 35 else total_vix_cost * (365 / dte_hedge)
        vix_cost_pct   = annual_vix / annual_income * 100 if annual_income else 0

        vv1, vv2, vv3 = st.columns(3)
        vv1.metric("Prämie gesamt",    f"${total_vix_cost:,.0f}")
        vv2.metric("Annualisiert",      f"${annual_vix:,.0f}")
        vv3.metric("% Jahresprämie",    f"{vix_cost_pct:.1f}%", delta_color="inverse")

        st.markdown("**Payout je Crash-Szenario**")
        vix_rows = []
        for label, drop in _SCENARIOS:
            port_loss   = _estimated_portfolio_loss(beta_notional, drop)
            vix_mult    = _VIX_AT_DROP.get(drop, 2.0)
            vix_at_drop = vix * vix_mult
            payout      = max(0, vix_at_drop - vix_strike) * 100 * n_vix
            net_vix     = payout - total_vix_cost
            covered_pct = min(100, payout / port_loss * 100) if port_loss > 0 else 0
            vix_rows.append({
                "Szenario":             label,
                "VIX erwartet":         f"{vix_at_drop:.0f}",
                "VIX Call Payout":      f"${payout:,.0f}",
                "Portfolio-Verlust":    f"${port_loss:,.0f}",
                "Abgedeckt":            f"{covered_pct:.0f}%",
                "Netto (nach Prämie)":  f"${net_vix:,.0f}",
                "Lohnt sich":           "✅" if net_vix > 0 else "❌",
            })
        st.dataframe(pd.DataFrame(vix_rows), use_container_width=True, hide_index=True)

        st.info(
            "💡 VIX Calls sind günstig wenn VIX niedrig ist (aktuell "
            f"{vix:.1f}) und explodieren bei Crash. Ideal als Ergänzung zum "
            "Put Spread — Put Spread schützt bei -10% bis -25%, "
            "VIX Call zahlt bei extremen Ereignissen (-35% und mehr)."
        )

    # ── Tab 4: Vergleich ──────────────────────────────────────────────────────
    with tab4:
        st.markdown("**Alle Hedge-Optionen im Kostenvergleich**")

        # Put Spread Kosten (aus Tab 2)
        hedge_options = []
        if spread:
            ann_ps = spread["total_cost"] * (365 / spread["dte"])
            hedge_options.append({
                "label":       f"{hedge_instrument} Put Spread ({hedge_pct*100:.0f}%)",
                "annual_cost": ann_ps,
                "description": f"{spread['n_contracts']} Kontrakte, "
                               f"${spread['short_strike']:.0f}/{spread['long_strike']:.0f}, "
                               f"Debit ${spread['net_debit']*100:.0f}/Spread",
            })
        # VIX Call Kosten
        n_vix_default = max(1, int(beta_notional / 50000))
        vix_call_default = vix * 0.08
        ann_vix = vix_call_default * 100 * n_vix_default * 12
        hedge_options.append({
            "label":       "VIX Call (OTM)",
            "annual_cost": ann_vix,
            "description": f"{n_vix_default} Kontrakte, Strike {vix_strike_default}, "
                           f"Prämie ~${vix_call_default:.2f} (Schätzung)",
        })
        # Kombination
        if spread:
            combined_ann = ann_ps * 0.6 + ann_vix  # kleinerer Spread + VIX
            hedge_options.append({
                "label":       "Kombination (60% Spread + VIX)",
                "annual_cost": combined_ann,
                "description": "Kleinerer Put Spread + VIX Call — breite Abdeckung",
            })

        # Vergleichstabelle
        comp_rows = []
        for h in hedge_options:
            pct = h["annual_cost"] / annual_income * 100 if annual_income else 0
            net = annual_income - h["annual_cost"]
            comp_rows.append({
                "Hedge-Option":           h["label"],
                "Jährl. Kosten":          f"${h['annual_cost']:,.0f}",
                "% der Jahresprämie":     f"{pct:.1f}%",
                "Verbleibende Nettoprofit": f"${net:,.0f}",
                "Bewertung":              "✅ Empfohlen" if pct < 15 else ("⚠️ Akzeptabel" if pct < 30 else "🚨 Teuer"),
                "Details":                h["description"],
            })
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)

        if hedge_options:
            st.plotly_chart(_chart_cost_vs_income(monthly_income, hedge_options),
                            use_container_width=True)

        st.markdown("---")
        st.markdown("**Daumenregel: Wann ist Hedging sinnvoll?**")
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("""
**Hedge kaufen wenn:**
- VIX < 20 (Versicherung ist günstig)
- Portfolio-Notional > $50k
- Viele offene Positionen gleichzeitig
- Earnings-Season läuft
""")
        with col_r2:
            st.markdown(f"""
**Aktuelle Situation:**
- VIX: {vix:.1f} → {"günstig für Hedge ✅" if vix < 20 else "teuer ⚠️" if vix < 30 else "sehr teuer 🚨"}
- Portfolio-Notional: ${total_notional:,.0f} → {"Hedge sinnvoll ✅" if total_notional > 50000 else "Optional"}
- Monatl. Prämie: ${monthly_income:,.0f}
""")


main()
