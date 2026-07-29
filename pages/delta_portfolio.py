"""
Delta Portfolio Tracker
=======================
Zeigt den Gesamt-Delta aller offenen Positionen (Aktien + Optionen).
Positionen werden in data/delta_positions.json gespeichert.
Delta-Werte werden bei jedem Seitenaufruf live aus der DB geladen.
"""

import json
import logging
import math
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))

# ── Persistenz-Datei ──────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSITIONS_FILE = os.path.join(BASE_DIR, "data", "delta_positions.json")


def _load_positions() -> list[dict]:
    if not os.path.exists(POSITIONS_FILE):
        return []
    try:
        with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_positions(positions: list[dict]):
    os.makedirs(os.path.dirname(POSITIONS_FILE), exist_ok=True)
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(positions, f, indent=2)


# ── Delta aus DB laden ────────────────────────────────────────────────────────
@st.cache_data(ttl=120)
def _fetch_option_delta(symbol: str, strike: float, expiry: str, contract_type: str) -> float | None:
    """Lädt aktuellen Delta für eine spezifische Option aus OptionDataMassive."""
    try:
        df = select_into_dataframe(
            query="""
                SELECT greeks_delta
                FROM "OptionDataMassive"
                WHERE symbol = :symbol
                  AND strike_price = :strike
                  AND expiration_date = :expiry
                  AND contract_type = :ctype
                LIMIT 1
            """,
            params={"symbol": symbol, "strike": strike, "expiry": expiry, "ctype": contract_type},
        )
        if df is not None and not df.empty:
            val = df.iloc[0]["greeks_delta"]
            return float(val) if pd.notna(val) else None
    except Exception as e:
        logger.warning(f"Delta fetch failed for {symbol}: {e}")
    return None


@st.cache_data(ttl=120)
def _fetch_stock_price(symbol: str) -> float | None:
    try:
        df = select_into_dataframe(
            query='SELECT close FROM "StockPricesYahoo" WHERE symbol = :symbol LIMIT 1',
            params={"symbol": symbol},
        )
        if df is not None and not df.empty:
            return float(df.iloc[0]["close"])
    except Exception:
        pass
    return None


# ── Delta-History aus DB ──────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def _fetch_delta_history(symbol: str, strike: float, expiry: str, contract_type: str) -> pd.DataFrame | None:
    try:
        df = select_into_dataframe(
            query="""
                SELECT date, greeks_delta
                FROM "OptionDataMassiveHistory"
                WHERE symbol = :symbol
                  AND strike_price = :strike
                  AND expiration_date = :expiry
                  AND contract_type = :ctype
                  AND date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY date ASC
            """,
            params={"symbol": symbol, "strike": strike, "expiry": expiry, "ctype": contract_type},
        )
        return df if df is not None and not df.empty else None
    except Exception:
        return None


# ── Seite ─────────────────────────────────────────────────────────────────────
st.title("📐 Delta Portfolio Tracker")
st.caption("Netto-Delta aller Positionen live aus der DB — bei jedem Seitenaufruf neu berechnet.")

# Session state
if "dpt_positions" not in st.session_state:
    st.session_state["dpt_positions"] = _load_positions()

positions: list[dict] = st.session_state["dpt_positions"]

# ── Position hinzufügen ───────────────────────────────────────────────────────
with st.expander("➕ Position hinzufügen", expanded=not positions):
    st.markdown("**Aktie (Long/Short Stock)**")
    sc1, sc2, sc3, sc4 = st.columns([2, 1, 1, 1])
    with sc1:
        s_symbol = st.text_input("Symbol", key="dpt_s_sym", placeholder="AAPL").upper().strip()
    with sc2:
        s_qty = st.number_input("Stück", min_value=1, value=100, step=1, key="dpt_s_qty")
    with sc3:
        s_dir = st.radio("Richtung", ["Long", "Short"], horizontal=True, key="dpt_s_dir")
    with sc4:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Aktie hinzufügen", key="dpt_add_stock"):
            if s_symbol:
                positions.append({
                    "type": "stock",
                    "symbol": s_symbol,
                    "qty": s_qty,
                    "direction": s_dir,
                })
                _save_positions(positions)
                st.session_state["dpt_positions"] = positions
                st.rerun()

    st.markdown("---")
    st.markdown("**Option (Long/Short)**")
    oc1, oc2, oc3, oc4, oc5, oc6, oc7 = st.columns([2, 1, 1, 1, 1, 1, 1])
    with oc1:
        o_symbol = st.text_input("Symbol", key="dpt_o_sym", placeholder="AAPL").upper().strip()
    with oc2:
        o_ctype = st.selectbox("Typ", ["call", "put"], key="dpt_o_type")
    with oc3:
        o_strike = st.number_input("Strike", min_value=0.0, value=150.0, step=1.0, format="%.1f", key="dpt_o_strike")
    with oc4:
        o_expiry = st.text_input("Verfall", key="dpt_o_expiry", placeholder="2026-08-15")
    with oc5:
        o_contracts = st.number_input("Kontrakte", min_value=1, value=1, step=1, key="dpt_o_qty")
    with oc6:
        o_dir = st.radio("Richtung", ["Long", "Short"], horizontal=True, key="dpt_o_dir")
    with oc7:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("Option hinzufügen", key="dpt_add_option"):
            if o_symbol and o_expiry:
                positions.append({
                    "type": "option",
                    "symbol": o_symbol,
                    "contract_type": o_ctype,
                    "strike": o_strike,
                    "expiry": o_expiry,
                    "contracts": o_contracts,
                    "direction": o_dir,
                })
                _save_positions(positions)
                st.session_state["dpt_positions"] = positions
                st.rerun()

if not positions:
    st.info("Noch keine Positionen. Oben eine Aktie oder Option hinzufügen.")
    st.stop()

# ── Delta berechnen ───────────────────────────────────────────────────────────
st.divider()

rows = []
total_delta = 0.0

for i, pos in enumerate(positions):
    sym      = pos["symbol"]
    p_type   = pos["type"]
    direction = pos.get("direction", "Long")
    sign     = 1 if direction == "Long" else -1

    if p_type == "stock":
        qty        = pos["qty"]
        raw_delta  = 1.0
        pos_delta  = sign * qty * raw_delta
        stock_px   = _fetch_stock_price(sym)
        notional   = stock_px * qty if stock_px else None
        rows.append({
            "idx":       i,
            "Symbol":    sym,
            "Typ":       f"{'📈' if direction=='Long' else '📉'} {direction} Stock",
            "Details":   f"{qty} Stück",
            "Delta/Einheit": f"{sign * raw_delta:+.2f}",
            "Pos.-Delta":    pos_delta,
            "Kurs":      f"${stock_px:.2f}" if stock_px else "—",
            "Notional":  f"${notional:,.0f}" if notional else "—",
            "Status":    "✅",
        })
        total_delta += pos_delta

    else:
        contracts  = pos["contracts"]
        strike     = pos["strike"]
        expiry     = pos["expiry"]
        ctype      = pos["contract_type"]
        raw_delta  = _fetch_option_delta(sym, strike, expiry, ctype)
        stock_px   = _fetch_stock_price(sym)

        if raw_delta is not None:
            pos_delta = sign * contracts * 100 * raw_delta
            status    = "✅"
        else:
            pos_delta = 0.0
            status    = "⚠️ kein Delta"

        rows.append({
            "idx":       i,
            "Symbol":    sym,
            "Typ":       f"{'🟢' if ctype=='call' else '🔴'} {direction} {ctype.capitalize()}",
            "Details":   f"Strike {strike:.0f} | Verfall {expiry} | {contracts} Kontrakte",
            "Delta/Einheit": f"{sign * raw_delta:+.3f}" if raw_delta is not None else "—",
            "Pos.-Delta":    pos_delta,
            "Kurs":      f"${stock_px:.2f}" if stock_px else "—",
            "Notional":  f"${stock_px * 100 * contracts:,.0f}" if stock_px else "—",
            "Status":    status,
        })
        total_delta += pos_delta

result_df = pd.DataFrame(rows)

# ── Gesamt-Delta Banner ───────────────────────────────────────────────────────
if total_delta > 50:
    _bg, _brd, _lbl = "#166534", "#22c55e", "🟢 BULLISH"
elif total_delta > 10:
    _bg, _brd, _lbl = "#854d0e", "#f59e0b", "🟡 LEICHT BULLISH"
elif total_delta >= -10:
    _bg, _brd, _lbl = "#1e3a5f", "#60a5fa", "🔵 ANNÄHERND NEUTRAL"
elif total_delta >= -50:
    _bg, _brd, _lbl = "#854d0e", "#f59e0b", "🟡 LEICHT BEARISH"
else:
    _bg, _brd, _lbl = "#7f1d1d", "#ef4444", "🔴 BEARISH"

st.markdown(
    f"<div style='background:{_bg};border:2px solid {_brd};border-radius:10px;"
    f"padding:14px 20px;margin-bottom:12px;'>"
    f"<span style='color:#fff;font-size:28px;font-weight:800;'>{_lbl}</span>"
    f"<span style='color:#e5e7eb;font-size:18px;font-weight:600;'> &nbsp;·&nbsp; "
    f"Netto-Delta: <span style='color:{_brd};'>{total_delta:+.1f}</span></span>"
    f"<br><span style='color:#9ca3af;font-size:12px;'>"
    f"Bei einer 1%-Bewegung des Marktes ändert sich dein Portfolio um ca. "
    f"<b style='color:#e5e7eb;'>{total_delta * 0.01:.2f} × Kurswert</b> pro Aktie."
    f"</span></div>",
    unsafe_allow_html=True,
)

# ── Metriken ──────────────────────────────────────────────────────────────────
m1, m2, m3, m4 = st.columns(4)
m1.metric("Netto-Delta", f"{total_delta:+.1f}")
m2.metric("Positionen", len(positions))
bullish  = sum(r["Pos.-Delta"] for r in rows if r["Pos.-Delta"] > 0)
bearish  = sum(r["Pos.-Delta"] for r in rows if r["Pos.-Delta"] < 0)
m3.metric("Bullish Delta", f"{bullish:+.1f}")
m4.metric("Bearish Delta", f"{bearish:+.1f}")

# ── Delta pro Position ────────────────────────────────────────────────────────
st.subheader("📊 Delta pro Position")

disp = result_df[["Symbol", "Typ", "Details", "Delta/Einheit", "Pos.-Delta", "Kurs", "Notional", "Status"]].copy()
disp["Pos.-Delta"] = disp["Pos.-Delta"].apply(lambda v: f"{v:+.1f}")

def _highlight_delta(row):
    try:
        val = float(row["Pos.-Delta"].replace("+", ""))
    except Exception:
        return [""] * len(row)
    if val > 0:
        return ["background-color: rgba(20,83,45,0.20)"] * len(row)
    if val < 0:
        return ["background-color: rgba(127,29,29,0.20)"] * len(row)
    return [""] * len(row)

st.dataframe(
    disp.style.apply(_highlight_delta, axis=1).hide(axis="index"),
    use_container_width=True,
    height=min(500, 40 + 35 * len(disp)),
)

# Positionen entfernen
with st.expander("🗑️ Position entfernen"):
    if rows:
        labels = [f"{r['Symbol']} — {r['Typ']} ({r['Details']})" for r in rows]
        to_remove = st.selectbox("Position auswählen", options=range(len(labels)),
                                  format_func=lambda i: labels[i], key="dpt_remove_sel")
        if st.button("Entfernen", key="dpt_remove_btn", type="secondary"):
            idx_to_remove = rows[to_remove]["idx"]
            positions.pop(idx_to_remove)
            _save_positions(positions)
            st.session_state["dpt_positions"] = positions
            st.rerun()
    if st.button("🗑️ Alle Positionen löschen", key="dpt_clear_all"):
        positions.clear()
        _save_positions(positions)
        st.session_state["dpt_positions"] = positions
        st.rerun()

# ── Hedge-Rechner ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("🧮 Hedge-Rechner")
st.caption("Wie viel brauche ich um delta-neutral zu werden?")

target_delta = st.number_input("Ziel-Delta", value=0.0, step=10.0, format="%.1f",
                                key="dpt_target", help="0 = vollständig neutral")
delta_to_hedge = total_delta - target_delta

if abs(delta_to_hedge) < 0.1:
    st.success("✅ Portfolio ist bereits nahe am Ziel-Delta.")
else:
    hedge_dir = "Short" if delta_to_hedge > 0 else "Long"
    st.markdown(
        f"Du musst **{abs(delta_to_hedge):+.1f} Delta {hedge_dir}** aufbauen um auf {target_delta:+.0f} zu kommen."
    )

    hedge_sym = st.text_input("Symbol für Hedge", key="dpt_hedge_sym", placeholder="AAPL").upper().strip()
    if hedge_sym:
        hedge_price = _fetch_stock_price(hedge_sym)
        if hedge_price:
            st.markdown(f"**Aktueller Kurs {hedge_sym}: ${hedge_price:.2f}**")
            st.markdown("**Mögliche Hedges:**")

            hc1, hc2 = st.columns(2)
            with hc1:
                shares_needed = abs(delta_to_hedge)
                st.markdown(
                    f"<div style='background:rgba(255,255,255,0.05);border-radius:8px;padding:12px 14px;'>"
                    f"<b>📈 Aktien-Hedge</b><br>"
                    f"{hedge_dir} <b>{shares_needed:.0f} Stück {hedge_sym}</b><br>"
                    f"<span style='color:#9ca3af;font-size:12px;'>Kosten: ~${shares_needed * hedge_price:,.0f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with hc2:
                # ATM-Put oder Call (Delta ca. ±0.50)
                atm_delta     = 0.50
                contracts_needed = math.ceil(abs(delta_to_hedge) / (atm_delta * 100))
                option_type   = "put" if delta_to_hedge > 0 else "call"
                st.markdown(
                    f"<div style='background:rgba(255,255,255,0.05);border-radius:8px;padding:12px 14px;'>"
                    f"<b>{'🔴 Put' if option_type=='put' else '🟢 Call'}-Hedge (ATM ~Δ0.50)</b><br>"
                    f"Kauf <b>{contracts_needed} ATM-{option_type.capitalize()}-Kontrakte {hedge_sym}</b><br>"
                    f"<span style='color:#9ca3af;font-size:12px;'>"
                    f"Ergibt ca. {hedge_dir} {contracts_needed * 100 * atm_delta:.0f} Delta</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# ── Delta-History Chart ───────────────────────────────────────────────────────
st.divider()
st.subheader("📈 Delta-Historie (letzte 60 Tage)")
st.caption("Delta-Verlauf der einzelnen Optionspositionen über Zeit.")

option_positions = [p for p in positions if p["type"] == "option"]
if not option_positions:
    st.caption("Keine Optionspositionen — History-Chart nur für Optionen verfügbar.")
else:
    _dark  = st.get_option("theme.base") != "light"
    _paper = "#1a1a2e" if _dark else "#ffffff"
    _plot  = "#16213e" if _dark else "#f8fafc"
    _text  = "#e2e8f0" if _dark else "#1e293b"
    _grid  = "rgba(255,255,255,0.08)" if _dark else "rgba(0,0,0,0.06)"

    fig = go.Figure()
    colors = ["#60a5fa", "#f59e0b", "#22c55e", "#a78bfa", "#f43f5e", "#34d399"]

    for i, pos in enumerate(option_positions):
        hist = _fetch_delta_history(pos["symbol"], pos["strike"], pos["expiry"], pos["contract_type"])
        if hist is None:
            continue
        hist["date"] = pd.to_datetime(hist["date"])
        hist["greeks_delta"] = pd.to_numeric(hist["greeks_delta"], errors="coerce")
        sign = 1 if pos.get("direction", "Long") == "Long" else -1
        hist["pos_delta"] = sign * pos["contracts"] * 100 * hist["greeks_delta"]

        label = f"{pos['symbol']} {pos['contract_type'].upper()} {pos['strike']:.0f} ({pos['expiry']})"
        fig.add_trace(go.Scatter(
            x=hist["date"], y=hist["pos_delta"],
            mode="lines", name=label,
            line=dict(color=colors[i % len(colors)], width=2),
            hovertemplate=f"{label}<br>%{{x|%d.%m.%Y}}<br>Delta: %{{y:+.1f}}<extra></extra>",
        ))

    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.3)", width=1, dash="dash"))
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor=_paper, plot_bgcolor=_plot,
        font=dict(color=_text, size=11),
        legend=dict(orientation="h", y=1.1, font_size=10),
        xaxis=dict(gridcolor=_grid, zeroline=False),
        yaxis=dict(title="Position-Delta", gridcolor=_grid, zeroline=False),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Delta Portfolio Tracker · Delta live aus OptionDataMassive · Positionen in data/delta_positions.json")
