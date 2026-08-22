"""
Portfolio Hedge Calculator
==========================
Lädt dein Portfolio, misst das Crash-Risiko (beta-gewichtet) und schlägt ECHTE
Absicherungen mit BEGRENZTEM Risiko vor — Long Put Spreads auf Index-ETFs.

Kernprinzip: Ein Hedge ist eine VERSICHERUNG. Er kostet eine begrenzte, im Voraus
bekannte Prämie und zahlt im Crash. Ein Short Put (Crash Hedge Finder alt) ist KEIN
Hedge — er hat unbegrenztes Tail-Risiko und verliert im selben Crash wie das Portfolio.

Alle Preise/Optionsdaten kommen live aus der DB (OptionDataMerged, StockPricesYahoo).
"""

import csv
import io
import logging
import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.database import select_into_dataframe

logger = logging.getLogger(os.path.basename(__file__))

# ── Beta-Fallback (wird durch DB-Beta überschrieben wo vorhanden) ─────────────
_BETA_MAP = {
    "META": 1.25, "GOOGL": 1.15, "GOOG": 1.15, "AMZN": 1.20, "NVDA": 1.60,
    "MSFT": 1.10, "AAPL": 1.10, "TSLA": 1.80, "CRM": 1.30, "PLTR": 1.70,
    "INTC": 1.20, "ORCL": 1.10, "WDAY": 1.35, "BE": 1.50, "SMCI": 1.90,
    "WMT": 0.55, "MRK": 0.75, "GILD": 0.75, "DHR": 1.00, "ZTS": 0.90,
    "BA": 1.35, "DAL": 1.40, "VLO": 1.10, "OKE": 0.85,
    "ISRG": 1.05, "UBER": 1.45, "CF": 1.10, "KO": 0.55, "PEP": 0.60,
}
_DEFAULT_BETA = 1.0

# Crash-Szenarien: Markteinbruch in % des Index
_SCENARIOS = [
    ("-5% Rücksetzer",   -0.05),
    ("-10% Korrektur",   -0.10),
    ("-20% Bärenmarkt",  -0.20),
    ("-35% Crash",       -0.35),
    ("-50% Krise",       -0.50),
]

_HEDGE_ETFS = {"SPY": "S&P 500", "QQQ": "Nasdaq 100"}


# ═══════════════════════════════════════════════════════════════════════════════
# CSV-Parser
# ═══════════════════════════════════════════════════════════════════════════════

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
        pc = (data.get("Put/Call", "") or "").strip().upper()

        if asset_class == "STK":
            positions.append({"type": "stock", "symbol": symbol_raw, "qty": qty,
                              "mark": mark, "strike": 0.0, "put_call": "",
                              "direction": "Long" if qty > 0 else "Short"})
        elif asset_class == "OPT":
            underlying = _extract_symbol(symbol_raw)
            if underlying:
                positions.append({"type": "option", "symbol": underlying, "qty": qty,
                                  "mark": mark, "strike": strike, "put_call": pc,
                                  "direction": "Long" if qty > 0 else "Short"})
    return positions


def _parse_trades_report(content: str) -> list[dict]:
    """Trades_Report: nettiert nach Symbol+Strike+Expiry+P/C → offene Positionen."""
    try:
        trades = list(csv.DictReader(io.StringIO(content)))
    except Exception:
        return []
    net = defaultdict(float)
    info = {}
    for t in trades:
        sym = t.get('Symbol', '').strip().split()[0]
        key = (sym, t.get('Strike', ''), t.get('Expiry', ''), t.get('Put/Call', ''))
        try:
            net[key] += float(t.get('Quantity', 0))
        except ValueError:
            pass
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
        positions.append({"type": "option", "symbol": sym, "qty": qty, "mark": mark,
                          "strike": strike_f, "put_call": (pc or "").strip().upper(),
                          "direction": "Long" if qty > 0 else "Short"})
    return positions


def _parse_csv(content: str) -> list[dict]:
    first = content.lstrip()
    if first.startswith('"ClientAccountID"') or first.startswith('ClientAccountID'):
        first_line = content.split('\n')[0]
        if 'Open/CloseIndicator' in first_line or 'FifoPnlRealized' in first_line:
            return _parse_trades_report(content)
        return _parse_position_report(content)
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# DB-Abfragen
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300)
def _fetch_price(symbol: str, fallback: float) -> float:
    try:
        df = select_into_dataframe(
            'SELECT close FROM "StockPricesYahoo" WHERE symbol = :sym ORDER BY date DESC LIMIT 1',
            params={"sym": symbol})
        if df is not None and not df.empty and pd.notnull(df.iloc[0, 0]):
            return float(df.iloc[0, 0])
    except Exception:
        pass
    return fallback


@st.cache_data(ttl=300)
def _fetch_put_chain(symbol: str, dte_min: int, dte_max: int) -> pd.DataFrame:
    """Volle Put-Kette eines Hedge-ETFs aus OptionDataMerged (Basis für Long Put Spreads)."""
    try:
        df = select_into_dataframe(
            """
            SELECT strike_price, day_close AS premium, days_to_expiration AS dte,
                   expiration_date, live_stock_price AS stock_price,
                   abs(greeks_delta) AS delta, implied_volatility AS iv, open_interest AS oi
            FROM "OptionDataMerged"
            WHERE symbol = :sym AND contract_type = 'put'
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND day_close > 0 AND open_interest >= 50
            ORDER BY expiration_date ASC, strike_price DESC
            """,
            params={"sym": symbol, "dte_min": dte_min, "dte_max": dte_max})
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"put chain query failed for {symbol}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def _fetch_portfolio_premiums(symbols: tuple[str, ...], dte_min: int, dte_max: int) -> pd.DataFrame:
    """Aktuelle Short-Put-Prämien (Delta ~0.20–0.35) der Portfolio-Symbole → Prämien-Schätzung."""
    if not symbols:
        return pd.DataFrame()
    try:
        df = select_into_dataframe(
            """
            SELECT symbol, strike_price, day_close AS premium, days_to_expiration AS dte,
                   abs(greeks_delta) AS delta, open_interest AS oi, iv_rank,
                   live_stock_price AS stock_price
            FROM "OptionDataMerged"
            WHERE symbol = ANY(:syms) AND contract_type = 'put'
              AND days_to_expiration BETWEEN :dte_min AND :dte_max
              AND abs(greeks_delta) BETWEEN 0.15 AND 0.35
              AND day_close > 0 AND open_interest >= 25
            ORDER BY symbol, abs(abs(greeks_delta) - 0.25)
            """,
            params={"syms": list(symbols), "dte_min": dte_min, "dte_max": dte_max})
        return df if df is not None else pd.DataFrame()
    except Exception as e:
        logger.warning(f"portfolio premium query failed: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=600)
def _fetch_betas(symbols: tuple[str, ...]) -> dict:
    if not symbols:
        return {}
    try:
        df = select_into_dataframe(
            'SELECT symbol, "KeyStats_beta" AS beta FROM "FundamentalData" WHERE symbol = ANY(:syms)',
            params={"syms": list(symbols)})
        if df is not None and not df.empty:
            return {r["symbol"]: float(r["beta"]) for _, r in df.iterrows()
                    if pd.notnull(r["beta"])}
    except Exception as e:
        logger.warning(f"beta query failed: {e}")
    return {}


# ═══════════════════════════════════════════════════════════════════════════════
# Risiko-Modell
# ═══════════════════════════════════════════════════════════════════════════════

def _portfolio_risk(positions: list[dict], beta_db: dict) -> dict:
    """
    Aggregiert das Downside-Risiko. Für Bull-Put-Spread-Portfolios ist das relevante
    Maß das beta-gewichtete Notional der SHORT Puts (dort sitzt das Crash-Risiko).
    """
    rows = []
    total_notional = 0.0
    beta_notional = 0.0
    short_syms = []

    for p in positions:
        # Nur Short Puts tragen das Crash-Downside (Bull Put Spread = short put + long put)
        is_short_put = (p.get("direction") == "Short"
                        and (p.get("put_call", "") in ("P", "") ))
        if p.get("type") != "option" or not is_short_put:
            continue
        sym = p["symbol"]
        strike = p.get("strike", 0.0)
        qty = abs(p.get("qty", 1))
        if strike <= 0:
            continue
        notional = strike * 100 * qty
        beta = beta_db.get(sym, _BETA_MAP.get(sym, _DEFAULT_BETA))
        bn = notional * beta
        total_notional += notional
        beta_notional += bn
        short_syms.append(sym)
        rows.append({"Symbol": sym, "Kontrakte": int(qty), "Strike": strike,
                     "Notional $": notional, "Beta": round(beta, 2), "Beta-Notional $": bn})

    return {"rows": rows, "total_notional": total_notional,
            "beta_notional": beta_notional, "symbols": sorted(set(short_syms))}


def _portfolio_loss(beta_notional: float, drop: float) -> float:
    """
    Erwarteter Portfolio-Verlust bei Markteinbruch `drop` (negativ).
    Short Puts verlieren wegen Gamma/Vega überproportional zum reinen Delta-Verlust,
    je tiefer der Crash. Multiplikator empirisch (2018/2020/2022 Volatilitätsschübe).
    """
    gamma_vega = 1.0 + abs(drop) * 0.9
    return beta_notional * abs(drop) * gamma_vega


def _long_put_spread_payout(long_strike: float, short_strike: float,
                            n_contracts: int, index_price: float, drop: float) -> float:
    """
    Echter Payoff eines LONG Put Spreads (kaufe long_strike Put, verkaufe short_strike Put,
    long_strike > short_strike) bei Index-Einbruch `drop`, bei Verfall.
    Intrinsischer Wert des Spreads = clamp(long_strike - price, 0, width) minus nichts
    (Debit ist separat als Kosten erfasst).
    """
    price_at_drop = index_price * (1 + drop)
    width = long_strike - short_strike
    intrinsic = min(max(long_strike - price_at_drop, 0.0), width)
    return intrinsic * 100 * n_contracts


def _build_hedge_variants(chain: pd.DataFrame, index_price: float,
                          beta_notional: float, hedge_pct: float,
                          target_dte: int) -> list[dict]:
    """
    Baut MEHRERE Long-Put-Spread-Vorschläge mit unterschiedlichem Schutzprofil.
    Jede Variante: Long-Put bei X% OTM, Short-Put weiter OTM (verbilligt die Versicherung).

    Rückgabe: Liste von Hedge-Dicts, jeweils mit echten Kosten + Kontraktzahl.
    """
    if chain.empty:
        return []

    # Auf den DTE-nächsten Verfall beschränken (ein sauberer Verfall pro Vorschlag)
    chain = chain.copy()
    chain["strike_price"] = pd.to_numeric(chain["strike_price"], errors="coerce")
    chain["premium"] = pd.to_numeric(chain["premium"], errors="coerce")
    chain = chain.dropna(subset=["strike_price", "premium"])
    if chain.empty:
        return []
    chain["dte_dist"] = (chain["dte"] - target_dte).abs()
    best_exp = chain.sort_values("dte_dist").iloc[0]["expiration_date"]
    leg = chain[chain["expiration_date"] == best_exp].copy()
    dte = int(leg["dte"].iloc[0])

    def _nearest(target_strike: float):
        idx = (leg["strike_price"] - target_strike).abs().idxmin()
        return leg.loc[idx]

    # Drei Schutzprofile: Long-Put-Strike bei -5% / -8% / -12% OTM,
    # Short-Put jeweils 8–10% unter dem Long-Put (Spread-Breite ~ Crash-Puffer).
    profiles = [
        ("Nah (−5% / −13%)",   -0.05, -0.13, "Fängt schon flache Rücksetzer, teurer"),
        ("Mittel (−8% / −18%)", -0.08, -0.18, "Guter Kompromiss Kosten/Schutz"),
        ("Katastrophe (−12% / −25%)", -0.12, -0.25, "Nur echte Crashs, sehr günstig"),
    ]

    variants = []
    protected_notional = beta_notional * hedge_pct

    for name, long_off, short_off, desc in profiles:
        long_target = index_price * (1 + long_off)
        short_target = index_price * (1 + short_off)
        long_leg = _nearest(long_target)
        short_leg = _nearest(short_target)
        long_strike = float(long_leg["strike_price"])
        short_strike = float(short_leg["strike_price"])
        if long_strike <= short_strike:
            continue
        long_prem = float(long_leg["premium"])
        short_prem = float(short_leg["premium"])
        net_debit = long_prem - short_prem
        if net_debit <= 0:
            continue
        width = long_strike - short_strike
        # Kontraktzahl: so viele Spreads, dass Max-Payout ≈ zu schützendes Notional × hedge_pct
        max_payout_per = width * 100
        n_contracts = max(1, round(protected_notional / max_payout_per)) if max_payout_per else 1
        total_debit = net_debit * 100 * n_contracts
        max_payout = width * 100 * n_contracts

        variants.append({
            "name": name, "desc": desc,
            "long_strike": long_strike, "long_prem": long_prem,
            "short_strike": short_strike, "short_prem": short_prem,
            "net_debit": net_debit, "width": width,
            "n_contracts": n_contracts, "total_debit": total_debit,
            "max_payout": max_payout, "dte": dte, "expiry": str(best_exp),
        })
    return variants


# ═══════════════════════════════════════════════════════════════════════════════
# Charts
# ═══════════════════════════════════════════════════════════════════════════════

def _chart_scenarios(beta_notional: float, hedge: dict | None,
                     index_price: float, monthly_income: float) -> go.Figure:
    labels = [s[0] for s in _SCENARIOS]
    drops = [s[1] for s in _SCENARIOS]
    raw = [_portfolio_loss(beta_notional, d) for d in drops]

    fig = go.Figure()
    fig.add_bar(name="Verlust ungesichert", x=labels, y=raw,
                marker_color="#ef4444", opacity=0.9)

    if hedge:
        hedged = []
        for l, d in zip(raw, drops):
            payout = _long_put_spread_payout(hedge["long_strike"], hedge["short_strike"],
                                             hedge["n_contracts"], index_price, d)
            net_loss = max(0, l - payout) + hedge["total_debit"]
            hedged.append(net_loss)
        fig.add_bar(name="Verlust nach Hedge (inkl. Prämie)", x=labels, y=hedged,
                    marker_color="#22c55e", opacity=0.9)

    if monthly_income:
        fig.add_hline(y=monthly_income * 12, line_dash="dot", line_color="#3b82f6",
                      annotation_text="Jahresprämie")
    fig.update_layout(title="Portfolio-Verlust: Ungesichert vs. mit Hedge", barmode="group",
                      yaxis_title="Verlust ($)", plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                      font_color="#e5e7eb", height=400, legend=dict(orientation="h", y=1.08))
    return fig


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    st.header("Portfolio Hedge Calculator")
    st.caption(
        "Lädt dein Portfolio, misst das Crash-Risiko und schlägt ECHTE Absicherungen "
        "mit begrenztem Risiko vor (Long Put Spreads) — Versicherungsprämie vs. Prämieneinnahmen."
    )

    with st.expander("ℹ️ Was ist hier ein 'echter' Hedge? (kurz lesen)", expanded=False):
        st.markdown("""
Ein **Hedge = Versicherung**: begrenzte, im Voraus bekannte Prämie, zahlt im Crash.

- ✅ **Long Put Spread** (hier vorgeschlagen): Du **kaufst** einen Index-Put und
  **verkaufst** einen weiter entfernten Put zur Verbilligung. **Max-Verlust = Debit**
  (die Prämie), fertig. Kein Tail-Risiko.
- ❌ **Short Put auf Gegenwerte** (alter Crash Hedge Finder): unbegrenztes Risiko, verliert
  im selben Crash wie dein Portfolio. Das ist **kein** Hedge, sondern eine zweite Wette.

Die zentrale Frage: **Ist die Versicherungsprämie < deine Prämieneinnahmen?**
Wenn ein Hedge 30–40% deiner Jahresprämie frisst und nur selten zahlt, lohnt er nicht.
Faustregel: unter ~20% der Jahresprämie = tragbar.
""")

    # ── Portfolio laden ───────────────────────────────────────────────────────
    st.subheader("1. Portfolio laden")
    cu, cm = st.columns([2, 1])
    with cu:
        uploaded = st.file_uploader("IBKR/CapTrader CSV", type=["csv"],
                                    help="Flex Query Position Report oder Trades_Report CSV")
    with cm:
        manual = st.text_area("Oder Short-Put-Symbole (kommagetrennt)",
                              placeholder="META, GOOGL, BA ...", height=68)

    positions: list[dict] = []
    if uploaded:
        try:
            content = uploaded.read().decode("utf-8", errors="ignore")
            positions = _parse_csv(content)
            st.success(f"{len(positions)} Positionen geladen") if positions else \
                st.warning("Format nicht erkannt (Flex Query Position Report / Trades_Report).")
        except Exception as e:
            st.error(f"Fehler: {e}")
    elif manual.strip():
        for s in [x.strip().upper() for x in manual.split(",") if x.strip()]:
            positions.append({"type": "option", "symbol": s, "qty": -1, "mark": 2.0,
                             "strike": 100.0, "put_call": "P", "direction": "Short"})

    if not positions:
        st.info("Bitte CSV hochladen oder Symbole eingeben.")
        return

    # ── Parameter ─────────────────────────────────────────────────────────────
    st.subheader("2. Hedge-Parameter")
    c1, c2, c3 = st.columns(3)
    with c1:
        hedge_pct = st.slider("Absicherungsgrad", 10, 100, 50, 5, format="%d%%",
                              help="Welcher Anteil des beta-gewichteten Risikos abgesichert werden soll") / 100
    with c2:
        dte_hedge = st.select_slider("Laufzeit Hedge (DTE)", [30, 45, 60, 90, 120], value=45)
    with c3:
        hedge_etf = st.selectbox("Hedge-Instrument", list(_HEDGE_ETFS.keys()),
                                 format_func=lambda k: f"{k} ({_HEDGE_ETFS[k]})")

    # ── Marktdaten + Risiko ─────────────────────────────────────────────────
    index_price = _fetch_price(hedge_etf, 560.0 if hedge_etf == "SPY" else 480.0)
    vix = _fetch_price("^VIX", 18.0)

    beta_db = _fetch_betas(tuple(sorted({p["symbol"] for p in positions})))
    risk = _portfolio_risk(positions, beta_db)
    beta_notional = risk["beta_notional"]
    total_notional = risk["total_notional"]

    if beta_notional <= 0:
        st.warning("Keine Short-Put-Positionen mit Strike erkannt. "
                   "Bitte Position Report / Trades_Report mit Strike-Daten hochladen.")
        return

    # Prämieneinnahmen aus DB
    df_prem = _fetch_portfolio_premiums(tuple(risk["symbols"]), 21, dte_hedge + 15)
    if not df_prem.empty:
        best = df_prem.sort_values("delta").groupby("symbol").first().reset_index()
        monthly_income = float((best["premium"] * 100).sum())
    else:
        monthly_income = total_notional * 0.004
    annual_income = monthly_income * 12

    st.subheader("3. Risiko & Absicherung")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("SPY/QQQ", f"${index_price:.2f}")
    k2.metric("VIX", f"{vix:.1f}", help="< 20 = Hedge günstig")
    k3.metric("Beta-Notional", f"${beta_notional:,.0f}", help="Crash-Risiko in Index-Einheiten")
    k4.metric("Monatl. Prämie", f"${monthly_income:,.0f}", help="Short-Put-Prämie aus DB, Delta ~0.25")
    k5.metric("Jahresprämie", f"${annual_income:,.0f}")

    # Hedge-Varianten bauen
    chain = _fetch_put_chain(hedge_etf, dte_hedge - 12, dte_hedge + 12)
    variants = _build_hedge_variants(chain, index_price, beta_notional, hedge_pct, dte_hedge)

    tab1, tab2, tab3 = st.tabs([
        "🛡️ Hedge-Vorschläge", "📉 Szenario-Analyse", "🥱 Portfolio-Details",
    ])

    # ── Tab 1: Hedge-Vorschläge ───────────────────────────────────────────────
    with tab1:
        if not variants:
            st.warning(f"Keine {hedge_etf}-Put-Kette für DTE ≈ {dte_hedge} in der DB. "
                       "DTE anpassen oder DB-Update abwarten.")
        else:
            st.markdown(f"**{len(variants)} Absicherungs-Varianten** auf {hedge_etf} "
                        f"({variants[0]['dte']} DTE, Verfall {variants[0]['expiry']}), "
                        f"jeweils Long Put Spread mit **begrenztem Risiko = Debit**.")

            # Übersichtstabelle aller Varianten
            rows = []
            for v in variants:
                annual_cost = v["total_debit"] * (365 / v["dte"]) if v["dte"] else v["total_debit"]
                cost_pct = annual_cost / annual_income * 100 if annual_income else 0
                rows.append({
                    "Variante": v["name"],
                    "Kauf Put": f"${v['long_strike']:.0f}",
                    "Verkauf Put": f"${v['short_strike']:.0f}",
                    "Kontrakte": v["n_contracts"],
                    "Prämie (Debit)": f"${v['total_debit']:,.0f}",
                    "Max Auszahlung": f"${v['max_payout']:,.0f}",
                    "Kosten/Jahr": f"${annual_cost:,.0f}",
                    "% Jahresprämie": f"{cost_pct:.0f}%",
                    "Bewertung": "✅" if cost_pct < 20 else ("⚠️" if cost_pct < 40 else "🚨"),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            st.markdown("---")
            # Detailkarten pro Variante
            for v in variants:
                annual_cost = v["total_debit"] * (365 / v["dte"]) if v["dte"] else v["total_debit"]
                cost_pct = annual_cost / annual_income * 100 if annual_income else 0
                leverage = v["max_payout"] / v["total_debit"] if v["total_debit"] else 0
                with st.container(border=True):
                    st.markdown(f"**{v['name']}** — {v['desc']}")
                    d1, d2, d3, d4 = st.columns(4)
                    d1.metric("Kaufe Put", f"${v['long_strike']:.0f}",
                              delta=f"−{(1-v['long_strike']/index_price)*100:.0f}% OTM")
                    d2.metric("Verkaufe Put", f"${v['short_strike']:.0f}",
                              delta=f"−{(1-v['short_strike']/index_price)*100:.0f}% OTM")
                    d3.metric("Versicherungsprämie", f"${v['total_debit']:,.0f}",
                              help=f"{v['n_contracts']} Spreads × ${v['net_debit']*100:.0f}")
                    d4.metric("Max Auszahlung", f"${v['max_payout']:,.0f}",
                              delta=f"{leverage:.0f}× Hebel")
                    # Payout je Szenario
                    pay_rows = []
                    for label, drop in _SCENARIOS:
                        payout = _long_put_spread_payout(v["long_strike"], v["short_strike"],
                                                         v["n_contracts"], index_price, drop)
                        port_loss = _portfolio_loss(beta_notional, drop)
                        net = payout - v["total_debit"]
                        offset = min(100, payout / port_loss * 100) if port_loss > 0 else 0
                        pay_rows.append({
                            "Szenario": label,
                            "Hedge zahlt": f"${payout:,.0f}",
                            "Portfolio-Verlust": f"${port_loss:,.0f}",
                            "Deckt ab": f"{offset:.0f}%",
                            "Netto (Payout − Prämie)": f"${net:,.0f}",
                        })
                    st.dataframe(pd.DataFrame(pay_rows), use_container_width=True, hide_index=True)
                    if cost_pct < 20:
                        st.success(f"✅ Kostet {cost_pct:.0f}% der Jahresprämie — tragbar.")
                    elif cost_pct < 40:
                        st.warning(f"⚠️ Kostet {cost_pct:.0f}% der Jahresprämie — spürbar. "
                                   "Ggf. Absicherungsgrad senken oder Katastrophen-Variante wählen.")
                    else:
                        st.error(f"🚨 Kostet {cost_pct:.0f}% der Jahresprämie — zu teuer für Dauerschutz. "
                                 "Nur situativ (z.B. vor Fed/CPI) oder Katastrophen-Variante.")

            if not df_prem.empty:
                with st.expander("Prämien-Basis aus DB (Short Puts Delta ~0.25)"):
                    show = df_prem[["symbol", "strike_price", "premium", "delta", "iv_rank", "dte"]].copy()
                    show.columns = ["Symbol", "Strike", "Prämie", "Delta", "IV Rank", "DTE"]
                    st.dataframe(show, use_container_width=True, hide_index=True)

    # ── Tab 2: Szenario-Analyse ───────────────────────────────────────────────
    with tab2:
        # Beste (mittlere) Variante für den Vergleichs-Chart
        default_hedge = variants[1] if len(variants) > 1 else (variants[0] if variants else None)
        rows = []
        for label, drop in _SCENARIOS:
            loss = _portfolio_loss(beta_notional, drop)
            months = loss / monthly_income if monthly_income else 0
            row = {"Szenario": label, "Markt": f"{drop*100:.0f}%",
                   "Verlust ungesichert": f"${loss:,.0f}",
                   "Erholung (Monate Prämie)": f"{months:.1f}"}
            if default_hedge:
                payout = _long_put_spread_payout(default_hedge["long_strike"],
                                                 default_hedge["short_strike"],
                                                 default_hedge["n_contracts"], index_price, drop)
                net_loss = max(0, loss - payout) + default_hedge["total_debit"]
                row["Verlust mit Hedge"] = f"${net_loss:,.0f}"
                row["Ersparnis"] = f"${loss - net_loss:,.0f}"
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.plotly_chart(_chart_scenarios(beta_notional, default_hedge, index_price, monthly_income),
                        use_container_width=True)
        if default_hedge:
            st.caption(f"Chart nutzt Variante **{default_hedge['name']}** als Referenz-Hedge.")

    # ── Tab 3: Portfolio-Details ──────────────────────────────────────────────
    with tab3:
        st.markdown("**Beta-gewichtetes Risiko der Short Puts**")
        if risk["rows"]:
            df_bw = pd.DataFrame(risk["rows"])
            df_bw["Notional $"] = df_bw["Notional $"].apply(lambda x: f"${x:,.0f}")
            df_bw["Beta-Notional $"] = df_bw["Beta-Notional $"].apply(lambda x: f"${x:,.0f}")
            st.dataframe(df_bw, use_container_width=True, hide_index=True)
        b1, b2, b3 = st.columns(3)
        b1.metric("Short Puts", len(risk["rows"]))
        b2.metric("Notional (worst case)", f"${total_notional:,.0f}")
        b3.metric("Beta-Notional", f"${beta_notional:,.0f}")
        st.caption("Beta aus FundamentalData (KeyStats_beta), Fallback aus interner Tabelle. "
                   "Beta-Notional = Summe(Strike × 100 × Kontrakte × Beta) — das ist das "
                   "SPY-äquivalente Crash-Risiko, gegen das abgesichert wird.")


main()
