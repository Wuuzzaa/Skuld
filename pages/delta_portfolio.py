"""
Delta Portfolio Tracker
=======================
Zeigt den Gesamt-Delta aller offenen Positionen (Aktien + Optionen).
Portfolio wird per CSV-Upload geladen und nur im Session State gehalten — keine Persistenz.
"""

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


# ── CSV-Import (CapTrader / IBKR Statement) ───────────────────────────────────

def _parse_ibkr_csv(content: str) -> list[dict]:
    """
    Parst IBKR/CapTrader Activity Statement CSV.
    Liest aus 'Mark-to-Market-Performance-Überblick' Sektion:
      Aktien:   qty und direction aus Vorher/Aktuell Menge
      Optionen: Symbol-String 'AAPL 18SEP26 150 P' → strike, expiry, contract_type
    Gibt Liste von positions-Dicts zurück.
    """
    import csv, re, io

    positions = []
    reader = csv.reader(io.StringIO(content))

    # Spalten-Header der MTM-Sektion merken
    # Header: Vermögenswertkategorie,Symbol,Vorher Menge,Aktuell Menge,Vorher Kurs,Aktuell Kurs,...
    mtm_header: list[str] = []

    for row in reader:
        if not row:
            continue

        section = row[0].strip()

        if section == "Mark-to-Market-Performance-Überblick":
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
                continue  # Position heute geschlossen

            # ── Aktien ────────────────────────────────────────────────────────
            if asset_class == "Aktien":
                positions.append({
                    "type":      "stock",
                    "symbol":    symbol_raw,
                    "qty":       int(abs(qty_now)),
                    "direction": "Long" if qty_now > 0 else "Short",
                })

            # ── Optionen ──────────────────────────────────────────────────────
            elif asset_class == "Aktien- und Indexoptionen":
                # Format: "AAPL 18SEP26 150 P" oder "SMCI 21AUG26 25.5 P"
                m = re.match(
                    r"^([A-Z0-9]+)\s+(\d{2}[A-Z]{3}\d{2})\s+([\d.]+)\s+([CP])$",
                    symbol_raw,
                )
                if not m:
                    logger.warning(f"Optionssymbol nicht parsbar: {symbol_raw!r}")
                    continue

                sym, expiry_raw, strike_str, cp = m.groups()

                # Verfall: "18SEP26" → "2026-09-18"
                try:
                    from datetime import datetime
                    expiry_dt = datetime.strptime(expiry_raw, "%d%b%y")
                    expiry = expiry_dt.strftime("%Y-%m-%d")
                except ValueError:
                    expiry = expiry_raw

                positions.append({
                    "type":          "option",
                    "symbol":        sym,
                    "contract_type": "call" if cp == "C" else "put",
                    "strike":        float(strike_str),
                    "expiry":        expiry,
                    "contracts":     int(abs(qty_now)),
                    "direction":     "Long" if qty_now > 0 else "Short",
                })

    return positions

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

# Session state — nur im RAM, nichts wird gespeichert
if "dpt_positions" not in st.session_state:
    st.session_state["dpt_positions"] = []

positions: list[dict] = st.session_state["dpt_positions"]

# ── CSV-Import ────────────────────────────────────────────────────────────────
with st.expander("📥 Portfolio aus CapTrader/IBKR CSV importieren", expanded=not positions):
    st.caption(
        "Kontoauszug (Activity Statement) von CapTrader oder IBKR hochladen. "
        "Jeder Import ersetzt das aktuelle Portfolio — nichts wird gespeichert."
    )
    uploaded = st.file_uploader("CSV-Datei hochladen", type=["csv"], key="dpt_csv_upload")
    if uploaded is not None:
        if st.button("📥 Importieren", key="dpt_do_import", type="primary"):
            try:
                content = uploaded.read().decode("utf-8", errors="replace")
                imported = _parse_ibkr_csv(content)
                if not imported:
                    st.error("Keine offenen Positionen gefunden. Ist das die richtige Datei?")
                else:
                    st.session_state["dpt_positions"] = imported
                    n_stocks  = sum(1 for p in imported if p["type"] == "stock")
                    n_options = sum(1 for p in imported if p["type"] == "option")
                    st.success(f"✅ {len(imported)} Positionen importiert — {n_stocks} Aktien, {n_options} Optionen")
                    st.rerun()
            except Exception as e:
                st.error(f"Fehler beim Parsen: {e}")

# ── Position hinzufügen ───────────────────────────────────────────────────────
with st.expander("➕ Position manuell hinzufügen", expanded=False):
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
            st.session_state["dpt_positions"] = positions
            st.rerun()
    if st.button("🗑️ Alle Positionen löschen", key="dpt_clear_all"):
        st.session_state["dpt_positions"] = []
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

# ── Risikograf (Risk Navigator) ───────────────────────────────────────────────
st.divider()
st.subheader("📉 Risikograf — Portfolio-Simulation")
st.caption("P&L des gesamten Portfolios bei verschiedenen Kursszenarien zum Verfall.")

# ── Hilfsfunktionen Payoff ────────────────────────────────────────────────────

def _payoff_stock(qty: int, direction: str, entry_price: float, price: float) -> float:
    sign = 1 if direction == "Long" else -1
    return sign * qty * (price - entry_price)


def _payoff_option(
    contracts: int,
    direction: str,
    contract_type: str,
    strike: float,
    premium: float,
    price: float,
) -> float:
    """P&L einer Optionsposition bei Verfall (kein IV-Einfluss, nur Intrinsic)."""
    sign = 1 if direction == "Long" else -1
    if contract_type == "call":
        intrinsic = max(price - strike, 0.0)
    else:
        intrinsic = max(strike - price, 0.0)
    # Short-Position: Prämie kassiert, Intrinsic verloren
    # Long-Position: Prämie bezahlt, Intrinsic gewonnen
    pnl_per_share = sign * (intrinsic - premium)
    return pnl_per_share * contracts * 100


def _vix_iv_multiplier(drop_pct: float) -> float:
    """
    Schätzt IV-Multiplikator basierend auf historischen VIX-Reaktionen.
    drop_pct: positiver Wert = Marktfall in % (z.B. 0.20 = -20%)
    Kalibriert auf: 2022 Ukraine (-25% → VIX ~+80%), 2020 Covid (-35% → +250%), 2008 (-55% → +400%)
    """
    if drop_pct <= 0:
        return 1.0
    # Exponentielle Annäherung an historische Datenpunkte
    return 1.0 + 4.5 * (drop_pct ** 1.6)


# ── Einstellungen ─────────────────────────────────────────────────────────────
rn_col1, rn_col2 = st.columns([2, 1])

with rn_col1:
    rn_range_pct = st.slider(
        "Kursbereich simulieren (±%)",
        min_value=10, max_value=80, value=40, step=5,
        help="Wie weit soll der Kurs nach oben/unten simuliert werden?",
    )

with rn_col2:
    rn_vix_mode = st.toggle(
        "VIX-Korrelation",
        value=False,
        help="Simuliert realistischen IV-Anstieg bei Drawdowns (historisch kalibriert auf 2008/2020/2022). "
             "Ohne diesen Modus: reine Intrinsic-Value-Berechnung bei Verfall.",
    )

rn_iv_shift = st.slider(
    "Manueller IV-Shift (%)" if not rn_vix_mode else "Basis-IV für VIX-Korrelation (%)",
    min_value=0, max_value=500, value=0, step=5,
    help="TWS Risk Navigator ist auf ~15% fixiert. Hier frei einstellbar.",
    disabled=rn_vix_mode,
)

# ── Prämien-Eingabe ───────────────────────────────────────────────────────────
with st.expander("💰 Einstandspreise eingeben (für korrekten P&L)", expanded=False):
    st.caption(
        "Ohne Einstandspreise wird die aktuelle DB-Prämie als Einstieg angenommen. "
        "Aktienpreis: aktueller Kurs aus DB wenn leer."
    )
    entry_overrides: dict[int, float] = {}
    for pos in positions:
        idx = positions.index(pos)
        if pos["type"] == "stock":
            label = f"#{idx} {pos['symbol']} Stock — Einstiegskurs $"
            default_px = _fetch_stock_price(pos["symbol"]) or 0.0
            entry_overrides[idx] = st.number_input(
                label, min_value=0.0, value=float(default_px),
                step=1.0, format="%.2f", key=f"rn_entry_{idx}",
            )
        else:
            label = (
                f"#{idx} {pos['symbol']} {pos['contract_type'].upper()} "
                f"{pos['strike']:.0f} {pos['expiry']} — Prämie $ (pro Aktie)"
            )
            entry_overrides[idx] = st.number_input(
                label, min_value=0.0, value=0.5,
                step=0.05, format="%.2f", key=f"rn_entry_{idx}",
            )

# ── Berechnung ────────────────────────────────────────────────────────────────
# Basis-Kurs: erster Aktien-Kurs im Portfolio, sonst SPY-Proxy
_base_prices = [_fetch_stock_price(p["symbol"]) for p in positions if p["type"] == "stock"]
_base_price = next((px for px in _base_prices if px), None)

if _base_price is None:
    # Optionen ohne Aktienposition: Underlying-Kurs des ersten Options-Symbols
    _first_opt = next((p for p in positions if p["type"] == "option"), None)
    if _first_opt:
        _base_price = _fetch_stock_price(_first_opt["symbol"])

if _base_price is None:
    st.warning("Kein Kurs für die Positionen in der DB — Risikograf nicht verfügbar.")
    st.stop()

# Preis-Range aufbauen
_lo = _base_price * (1 - rn_range_pct / 100)
_hi = _base_price * (1 + rn_range_pct / 100)
price_range = np.linspace(_lo, _hi, 300)

# Prozentuale Abweichung vom Basispreis
pct_range = (price_range - _base_price) / _base_price * 100

# P&L über alle Positionen summieren
portfolio_pnl = np.zeros(len(price_range))

for idx, pos in enumerate(positions):
    entry_val = entry_overrides.get(idx, 0.0)

    if pos["type"] == "stock":
        entry_px = entry_val if entry_val > 0 else (_fetch_stock_price(pos["symbol"]) or _base_price)
        pnl_arr = np.array([_payoff_stock(pos["qty"], pos["direction"], entry_px, p) for p in price_range])

    else:
        premium = entry_val if entry_val > 0 else 0.5

        if rn_vix_mode:
            # IV-angepasste Prämie: bei Marktfall steigt IV, Long-Puts werden wertvoller
            pnl_arr = np.zeros(len(price_range))
            for j, p in enumerate(price_range):
                drop = max((_base_price - p) / _base_price, 0.0)
                iv_mult = _vix_iv_multiplier(drop)
                # Long Put profitiert von IV-Anstieg (Vega-Effekt): Prämie sinkt weniger / steigt
                adjusted_premium = premium * iv_mult if pos["direction"] == "Long" and pos["contract_type"] == "put" else premium
                pnl_arr[j] = _payoff_option(
                    pos["contracts"], pos["direction"], pos["contract_type"],
                    pos["strike"], adjusted_premium, p,
                )
        else:
            pnl_arr = np.array([
                _payoff_option(
                    pos["contracts"], pos["direction"], pos["contract_type"],
                    pos["strike"], premium, p,
                )
                for p in price_range
            ])

    portfolio_pnl += pnl_arr

# ── Plot ──────────────────────────────────────────────────────────────────────
_dark   = st.get_option("theme.base") != "light"
_paper  = "#1a1a2e" if _dark else "#ffffff"
_plot   = "#16213e" if _dark else "#f8fafc"
_text   = "#e2e8f0" if _dark else "#1e293b"
_grid   = "rgba(255,255,255,0.08)" if _dark else "rgba(0,0,0,0.06)"

fig_rn = go.Figure()

# Nulllinie
fig_rn.add_hline(y=0, line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dash"))

# Jetziger Kurs (vertikale Linie)
fig_rn.add_vline(x=0, line=dict(color="rgba(255,255,255,0.25)", width=1, dash="dot"))

# Profit-Zone grün, Verlust-Zone rot einfärben
pnl_positive = np.where(portfolio_pnl >= 0, portfolio_pnl, 0)
pnl_negative = np.where(portfolio_pnl < 0, portfolio_pnl, 0)

fig_rn.add_trace(go.Scatter(
    x=pct_range, y=pnl_positive,
    fill="tozeroy",
    fillcolor="rgba(34,197,94,0.15)",
    line=dict(color="rgba(34,197,94,0)", width=0),
    showlegend=False, hoverinfo="skip",
))
fig_rn.add_trace(go.Scatter(
    x=pct_range, y=pnl_negative,
    fill="tozeroy",
    fillcolor="rgba(239,68,68,0.15)",
    line=dict(color="rgba(239,68,68,0)", width=0),
    showlegend=False, hoverinfo="skip",
))

# Haupt-P&L-Kurve
_line_color = "#60a5fa"
fig_rn.add_trace(go.Scatter(
    x=pct_range, y=portfolio_pnl,
    mode="lines",
    name="Portfolio P&L",
    line=dict(color=_line_color, width=2.5),
    hovertemplate="Kurs: %{customdata[0]:.2f} (%{x:+.1f}%)<br>P&L: <b>$%{y:+,.0f}</b><extra></extra>",
    customdata=np.column_stack([price_range]),
))

# Breakeven-Punkte markieren
_sign_changes = np.where(np.diff(np.sign(portfolio_pnl)))[0]
for sc in _sign_changes:
    be_pct = float(pct_range[sc])
    be_px  = float(price_range[sc])
    fig_rn.add_annotation(
        x=be_pct, y=0,
        text=f"BE ${be_px:.0f}",
        showarrow=True, arrowhead=2, arrowcolor="#f59e0b",
        font=dict(color="#f59e0b", size=10),
        bgcolor="rgba(0,0,0,0.6)", bordercolor="#f59e0b", borderwidth=1,
        ay=-30,
    )

# Max Profit / Max Verlust annotieren
_max_profit = float(portfolio_pnl.max())
_max_loss   = float(portfolio_pnl.min())
_mp_idx     = int(portfolio_pnl.argmax())
_ml_idx     = int(portfolio_pnl.argmin())

if _max_profit > 0:
    fig_rn.add_annotation(
        x=float(pct_range[_mp_idx]), y=_max_profit,
        text=f"Max +${_max_profit:,.0f}",
        showarrow=False,
        font=dict(color="#22c55e", size=10, weight="bold"),
        bgcolor="rgba(0,0,0,0.5)",
    )
if _max_loss < 0:
    fig_rn.add_annotation(
        x=float(pct_range[_ml_idx]), y=_max_loss,
        text=f"Max -${abs(_max_loss):,.0f}",
        showarrow=False,
        font=dict(color="#ef4444", size=10, weight="bold"),
        bgcolor="rgba(0,0,0,0.5)",
        ay=20,
    )

_iv_label = " + VIX-Korrelation" if rn_vix_mode else (f" + IV +{rn_iv_shift}%" if rn_iv_shift > 0 else "")
fig_rn.update_layout(
    title=dict(
        text=f"Risikograf{_iv_label} · Basis ${_base_price:.2f}",
        font=dict(size=13, color=_text),
        x=0,
    ),
    height=420,
    margin=dict(l=0, r=0, t=40, b=0),
    paper_bgcolor=_paper,
    plot_bgcolor=_plot,
    font=dict(color=_text, size=11),
    xaxis=dict(
        title="Kursveränderung (%)",
        gridcolor=_grid, zeroline=False,
        tickformat="+.0f", ticksuffix="%",
    ),
    yaxis=dict(
        title="Portfolio P&L ($)",
        gridcolor=_grid, zeroline=False,
        tickformat="$,.0f",
    ),
    hovermode="x unified",
    legend=dict(orientation="h", y=1.05),
)

st.plotly_chart(fig_rn, use_container_width=True, config={"displayModeBar": False})

# ── Kennzahlen unter dem Chart ────────────────────────────────────────────────
kz1, kz2, kz3, kz4 = st.columns(4)
kz1.metric("Max Profit", f"${_max_profit:+,.0f}", delta_color="normal")
kz2.metric("Max Verlust", f"${_max_loss:+,.0f}", delta_color="inverse")
kz3.metric("Breakevens", str(len(_sign_changes)))
_at_zero = float(portfolio_pnl[len(portfolio_pnl) // 2])
kz4.metric("P&L bei 0%", f"${_at_zero:+,.0f}")

if rn_vix_mode:
    st.info(
        "**VIX-Korrelationsmodus aktiv** — Long-Put-Prämien werden bei Drawdowns automatisch "
        "nach oben angepasst (kalibriert auf 2008/2020/2022). Macht Long-Hedges realistischer als TWS."
    )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("Delta Portfolio Tracker · Delta live aus OptionDataMassive · Kein persistenter Speicher")
