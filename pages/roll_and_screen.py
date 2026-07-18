"""
Roll & Screen — Wheel-Ablauf für Cash-Secured Puts.

Zwei Tabs:
  * Screener (Neuer Einstieg): qualifizierte Aktie + bester Put  [Task Schritt 5]
  * Roller  (Rollen):         historischen Put -> G/V -> 3 Roll-Stufen mit Ampel

Grundlage: "Optionen unschlagbar handeln", Kap. 3 (Rollen), 4+5 (Screener).
Roll-Rechenlogik: src/roll_support_calc.py (buchverifiziert, unit-getestet).

Persistenz: keine (session-only). Kernberechnungen werden bewusst NICHT gecacht;
nur reine DB-Reads nutzen @st.cache_data (Muster spreads_backtesting.py).
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from config import PATH_DATABASE_QUERY_FOLDER, RISK_FREE_RATE
from src.database import select_into_dataframe
from src.streamlit_helpers import render_date_filter
from src.page_display_dataframe import page_display_dataframe
from src.ui_utils import filter_by_expiration_type
from src.utils.option_utils import get_expiration_type
from src.black_scholes import PutValue
from src.roll_support_calc import position_status, roll_candidate, roll_candidate_explained
from src.put_screener import (
    score_candidates, score_breakdown, put_metrics, put_evaluation,
    DEFAULT_PE_MAX, DEFAULT_MIN_PUFFER_PCT,
)
from src.sector_rotation import (
    RotationParameters, load_sector_rotation_price_history,
    calculate_sector_rotation, build_latest_sector_snapshot, SECTOR_ETFS,
)

logger = logging.getLogger(os.path.basename(__file__))


# ---------------------------------------------------------------------------
# Dark-Theme CSS — Bloomberg-Desk Aesthetic
# ---------------------------------------------------------------------------
def _inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@300;400;500;600&display=swap');

    :root {
        --bg-base:      #080c17;
        --bg-card:      #0d1426;
        --bg-card2:     #111827;
        --bg-border:    #1e2d45;
        --teal:         #00d4aa;
        --teal-dim:     rgba(0,212,170,0.15);
        --amber:        #f59e0b;
        --amber-dim:    rgba(245,158,11,0.15);
        --red:          #ef4444;
        --red-dim:      rgba(239,68,68,0.15);
        --green:        #22c55e;
        --text-primary: #e2e8f0;
        --text-muted:   #64748b;
        --text-dim:     #94a3b8;
        --mono:         'JetBrains Mono', monospace;
        --sans:         'DM Sans', sans-serif;
    }

    /* Base overrides */
    .stApp { background: var(--bg-base) !important; font-family: var(--sans); }
    .stTabs [data-baseweb="tab-list"] { background: var(--bg-card); border-radius: 8px; padding: 4px; gap: 4px; }
    .stTabs [data-baseweb="tab"] { color: var(--text-muted) !important; border-radius: 6px; padding: 8px 20px; font-family: var(--sans); font-weight: 500; }
    .stTabs [aria-selected="true"] { background: var(--bg-border) !important; color: var(--teal) !important; }

    /* Metric overrides */
    [data-testid="stMetric"] { background: var(--bg-card2); border: 1px solid var(--bg-border); border-radius: 8px; padding: 12px 16px; }
    [data-testid="stMetricLabel"] { color: var(--text-muted) !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.08em; font-family: var(--sans); }
    [data-testid="stMetricValue"] { color: var(--text-primary) !important; font-family: var(--mono) !important; font-size: 1.4rem !important; }

    /* Dataframe */
    .stDataFrame { border: 1px solid var(--bg-border) !important; border-radius: 8px; overflow: hidden; }

    /* Buttons */
    .stButton > button[kind="primary"] {
        background: var(--teal) !important; color: #000 !important; font-weight: 600;
        border: none; border-radius: 6px; font-family: var(--sans);
    }
    .stButton > button[kind="secondary"] {
        background: var(--bg-card2) !important; color: var(--teal) !important;
        border: 1px solid var(--teal) !important; border-radius: 6px; font-family: var(--sans);
    }

    /* Expander */
    .streamlit-expanderHeader { background: var(--bg-card) !important; border: 1px solid var(--bg-border) !important; border-radius: 8px; color: var(--text-dim) !important; }

    /* Mono numbers in tables */
    .mono { font-family: var(--mono); }

    /* Divider */
    hr { border-color: var(--bg-border) !important; }
    </style>
    """, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------
def _parse_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


# ---------------------------------------------------------------------------
# DB-Loader (alle gecacht außer Live-Preise)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def _load_symbols():
    df = select_into_dataframe(
        query='SELECT DISTINCT symbol FROM "OptionDataMerged" ORDER BY symbol ASC',
    )
    if df is None or df.empty:
        return []
    return df["symbol"].dropna().astype(str).tolist()


@st.cache_data(ttl=600)
def _load_sector_quadrants() -> dict:
    """Gibt {sector_en: quadrant} zurück — identisch zur Sektor-Rotation-Seite."""
    try:
        params = RotationParameters()
        today = date.today().isoformat()
        price_history = load_sector_rotation_price_history(today, params)
        if price_history is None or price_history.empty:
            return {}
        rotation_data = calculate_sector_rotation(price_history, params)
        if rotation_data.empty:
            return {}
        snapshot = build_latest_sector_snapshot(rotation_data)
        # SECTOR_ETFS: {ETF: sector_name_de} — wir brauchen EN-Namen für den Match mit StockData
        etf_to_en = {
            "XLC": "Communication Services", "XLY": "Consumer Cyclical",
            "XLP": "Consumer Defensive",     "XLE": "Energy",
            "XLF": "Financial Services",     "XLV": "Healthcare",
            "XLI": "Industrials",            "XLB": "Basic Materials",
            "XLRE": "Real Estate",           "XLK": "Technology",
            "XLU": "Utilities",
        }
        result = {}
        for _, row in snapshot.iterrows():
            etf = row["symbol"]
            en = etf_to_en.get(etf)
            if en:
                result[en] = row["quadrant"]
        return result
    except Exception:
        return {}


@st.cache_data(ttl=300)
def _load_put_history(symbol, entry_date, dte_min, dte_max):
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_put_history.sql",
        params={"symbol": symbol, "entry_date": str(entry_date),
                "dte_min": int(dte_min), "dte_max": int(dte_max)},
    )


@st.cache_data(ttl=300)
def _load_roll_candidates(symbol, K, dte_min, dte_max,
                          min_oi=50, min_vol=10, delta_min=-1.0, delta_max=-0.05):
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "roll_candidates.sql",
        params={"symbol": symbol, "K": float(K),
                "dte_min": int(dte_min), "dte_max": int(dte_max),
                "min_oi": int(min_oi), "min_vol": int(min_vol),
                "delta_min": float(delta_min), "delta_max": float(delta_max)},
    )


@st.cache_data(ttl=300)
def _load_iv_history(symbol: str) -> pd.DataFrame | None:
    """Historische IV + IV-Rank für den Chart — letztes Jahr direkt in SQL begrenzt."""
    return select_into_dataframe(
        query="""
            SELECT date, symbol,
                   ROUND(iv::numeric * 100, 2)         AS iv,
                   ROUND(iv_rank::numeric, 2)           AS iv_rank,
                   ROUND(iv_percentile::numeric, 2)     AS iv_percentile
            FROM "StockImpliedVolatilityMassiveHistory"
            WHERE symbol = :symbol
              AND date >= CURRENT_DATE - INTERVAL '365 days'
              AND date <= CURRENT_DATE
            ORDER BY date ASC
        """,
        params={"symbol": symbol},
    )


def _current_put_price(option_osi, symbol):
    sql = """
        SELECT a.day_close AS premium_option_price, a.date
        FROM (
            SELECT date, option_osi, symbol, day_close FROM "OptionDataMassiveHistory"
            WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, option_osi, symbol, day_close FROM "OptionDataMassive"
        ) AS a
        WHERE a.option_osi = :osi AND a.symbol = :symbol
          AND a.date <= CURRENT_DATE
        ORDER BY a.date DESC
        LIMIT 1
    """
    df = select_into_dataframe(query=sql, params={"osi": option_osi, "symbol": symbol})
    if df is not None and not df.empty:
        d = df.iloc[0]["date"]
        return float(df.iloc[0]["premium_option_price"]), f"DB day_close ({d})"
    return None, "kein Preis in DB"


def _current_stock_price(symbol):
    sql = """
        SELECT b.close, b.date
        FROM (
            SELECT * FROM "StockPricesYahooHistory" WHERE date <> CURRENT_DATE
            UNION ALL
            SELECT CURRENT_DATE AS date, * FROM "StockPricesYahoo"
        ) AS b
        WHERE b.symbol = :symbol
          AND b.date <= CURRENT_DATE
          AND b.date >= CURRENT_DATE - INTERVAL '1 week'
        ORDER BY b.date DESC
        LIMIT 1
    """
    df = select_into_dataframe(query=sql, params={"symbol": symbol})
    if df is not None and not df.empty:
        return float(df.iloc[0]["close"])
    return None


# ---------------------------------------------------------------------------
# Quadrant-Helpers
# ---------------------------------------------------------------------------
_QUADRANT_EMOJI = {
    "Leading":   "🟢",
    "Improving": "🟡",
    "Weakening": "🟠",
    "Lagging":   "🔴",
    "Unbekannt": "⚪",
}
_QUADRANT_COLOR = {
    "Leading":   "#00d4aa",
    "Improving": "#f59e0b",
    "Weakening": "#f97316",
    "Lagging":   "#ef4444",
    "Unbekannt": "#64748b",
}


def _sector_badge_html(sector: str, quadrant: str) -> str:
    emoji = _QUADRANT_EMOJI.get(quadrant, "⚪")
    color = _QUADRANT_COLOR.get(quadrant, "#64748b")
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f'background:rgba(255,255,255,0.05);border:1px solid {color}44;'
        f'border-radius:20px;padding:3px 10px;font-size:12px;color:{color};'
        f'font-family:\'DM Sans\',sans-serif;font-weight:500;">'
        f'{emoji} {sector} · {quadrant}</span>'
    )


# ---------------------------------------------------------------------------
# IV-Rank Chart
# ---------------------------------------------------------------------------
def _render_iv_chart(symbol: str):
    iv_df = _load_iv_history(symbol)
    if iv_df is None or iv_df.empty:
        st.caption("Keine IV-Rank-Historie verfügbar.")
        return

    iv_df = iv_df.sort_values("date")
    iv_df["date"] = pd.to_datetime(iv_df["date"])

    # Percentil-Bänder über den Zeitraum
    iv_vals = iv_df["iv_rank"].dropna()
    p25 = iv_vals.quantile(0.25)
    p50 = iv_vals.quantile(0.50)
    p75 = iv_vals.quantile(0.75)

    fig = go.Figure()

    # 75-Percentil-Band (rot-Zone: teuer zu kaufen, gut zum Verkaufen)
    fig.add_hrect(y0=p75, y1=100, fillcolor="rgba(239,68,68,0.07)",
                  line_width=0, annotation_text="Hohe IV (gut für Prämienverkäufer)",
                  annotation_position="top left",
                  annotation_font=dict(color="#ef4444", size=10))

    # 25-Percentil-Band (grün-Zone)
    fig.add_hrect(y0=0, y1=p25, fillcolor="rgba(34,197,94,0.07)",
                  line_width=0, annotation_text="Niedrige IV",
                  annotation_position="bottom left",
                  annotation_font=dict(color="#22c55e", size=10))

    # Percentil-Linien
    for val, color, label in [(p25, "#22c55e", "P25"), (p50, "#64748b", "P50"), (p75, "#ef4444", "P75")]:
        fig.add_hline(y=val, line_dash="dash", line_color=color, line_width=1,
                      annotation_text=f"{label}: {val:.0f}",
                      annotation_font=dict(color=color, size=10))

    # IV-Rank Area
    fig.add_trace(go.Scatter(
        x=iv_df["date"], y=iv_df["iv_rank"],
        mode="lines", name="IV-Rank",
        line=dict(color="#00d4aa", width=2),
        fill="tozeroy",
        fillcolor="rgba(0,212,170,0.12)",
        hovertemplate="<b>%{x|%d.%m.%Y}</b><br>IV-Rank: %{y:.1f}<extra></extra>",
    ))

    # IV-Percentile als zweite Linie (gedimmt)
    if "iv_percentile" in iv_df.columns and iv_df["iv_percentile"].notna().any():
        fig.add_trace(go.Scatter(
            x=iv_df["date"], y=iv_df["iv_percentile"],
            mode="lines", name="IV-Percentile",
            line=dict(color="#f59e0b", width=1.5, dash="dot"),
            opacity=0.7,
            hovertemplate="<b>%{x|%d.%m.%Y}</b><br>IV-%ile: %{y:.1f}<extra></extra>",
        ))

    fig.update_layout(
        height=260,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(13,20,38,0.6)",
        font=dict(family="JetBrains Mono, monospace", color="#94a3b8", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        xaxis=dict(showgrid=False, zeroline=False, color="#64748b"),
        yaxis=dict(showgrid=True, gridcolor="#1e2d45", zeroline=False,
                   range=[0, 100], color="#64748b", title="IV-Rank"),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Aktueller Wert + Einordnung
    latest = iv_df.iloc[-1]
    rank_now = latest.get("iv_rank")
    if rank_now is not None and pd.notna(rank_now):
        if rank_now >= p75:
            zone = "🔴 **hoch** — Prämien sind überdurchschnittlich hoch: guter Zeitpunkt für Prämienverkauf"
        elif rank_now <= p25:
            zone = "🟢 **niedrig** — IV im unteren Quartil: Prämien eher mager"
        else:
            zone = "🟡 **mittel** — IV im normalen Bereich"
        st.caption(f"Aktueller IV-Rank: **{rank_now:.1f}** — {zone}")


# ---------------------------------------------------------------------------
# Position-Card HTML (Roller)
# ---------------------------------------------------------------------------
def _render_position_card(symbol: str, K: float, S: float, p_today_share: float,
                           P_eroeffnung: float, P_heute: float, n: int,
                           expiration_date, price_src: str):
    pos = position_status(K=K, S=S, P_eroeffnung=P_eroeffnung, P_heute=P_heute, n=int(n))
    dte_rest = (_parse_date(expiration_date) - date.today()).days

    pnl_pct = pos["pnl_pct"]
    pnl_abs = pos["pnl_abs"]
    # Balken: 0% = neutral (grau), positiv = teal, negativ = rot
    bar_pct = min(abs(pnl_pct), 100)
    bar_color = "#00d4aa" if pnl_pct >= 0 else "#ef4444"
    pnl_sign = "+" if pnl_pct >= 0 else ""
    pnl_abs_sign = "+" if pnl_abs >= 0 else ""
    status_label = "IM GEWINN" if pnl_pct >= 0 else "IM VERLUST"
    status_color = "#00d4aa" if pnl_pct >= 0 else "#ef4444"

    html = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=DM+Sans:wght@300;400;500;600&display=swap');
    .pos-card {{
        background: linear-gradient(135deg, #0d1426 0%, #111827 100%);
        border: 1px solid #1e2d45;
        border-radius: 12px;
        padding: 20px 24px;
        font-family: 'DM Sans', sans-serif;
        margin-bottom: 4px;
    }}
    .pos-header {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 16px;
    }}
    .pos-symbol {{
        font-size: 22px;
        font-weight: 600;
        color: #e2e8f0;
        letter-spacing: 0.05em;
    }}
    .pos-status {{
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.12em;
        padding: 4px 12px;
        border-radius: 20px;
        color: {status_color};
        background: {status_color}22;
        border: 1px solid {status_color}44;
    }}
    .pos-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin-bottom: 16px;
    }}
    .pos-cell {{ }}
    .pos-label {{
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #64748b;
        margin-bottom: 4px;
    }}
    .pos-value {{
        font-family: 'JetBrains Mono', monospace;
        font-size: 16px;
        font-weight: 600;
        color: #e2e8f0;
    }}
    .pos-value.teal {{ color: #00d4aa; }}
    .pos-value.red {{ color: #ef4444; }}
    .pos-bar-wrap {{
        background: #1e2d45;
        border-radius: 4px;
        height: 6px;
        overflow: hidden;
        margin-top: 4px;
    }}
    .pos-bar {{
        height: 6px;
        border-radius: 4px;
        background: {bar_color};
        width: {bar_pct:.1f}%;
        transition: width 0.4s ease;
    }}
    .pos-footer {{
        font-size: 11px;
        color: #64748b;
        margin-top: 8px;
    }}
    </style>
    <div class="pos-card">
        <div class="pos-header">
            <div class="pos-symbol">{symbol} · ${K:.2f} Put · {n}×</div>
            <div class="pos-status">{status_label} {pnl_sign}{pnl_pct:.1f}%</div>
        </div>
        <div class="pos-grid">
            <div class="pos-cell">
                <div class="pos-label">Aktienkurs</div>
                <div class="pos-value">${S:.2f}</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">Put heute</div>
                <div class="pos-value">${p_today_share:.2f}</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">G/V absolut</div>
                <div class="pos-value {'teal' if pnl_abs >= 0 else 'red'}">{pnl_abs_sign}${abs(pnl_abs):.2f}</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">DTE Rest</div>
                <div class="pos-value">{dte_rest} T</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">Innerer Wert</div>
                <div class="pos-value">${pos['inner_value']:.2f}</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">Restzeitwert</div>
                <div class="pos-value">${pos['time_value']:.2f}</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">Gewinnschwelle</div>
                <div class="pos-value">${pos['breakeven_old']:.2f}</div>
            </div>
            <div class="pos-cell">
                <div class="pos-label">P/L-Balken</div>
                <div class="pos-bar-wrap"><div class="pos-bar"></div></div>
                <div style="font-size:10px;color:#64748b;margin-top:3px;">{pnl_sign}{pnl_pct:.1f}% von max. ±100%</div>
            </div>
        </div>
        <div class="pos-footer">Kursquelle: {price_src}</div>
    </div>
    """
    components.html(html, height=220)
    return pos


# ---------------------------------------------------------------------------
# Tab 2 — Roller
# ---------------------------------------------------------------------------
def render_roller_tab():
    st.subheader("🔄 Roller — bestehenden Cash-Secured Put rollen")

    with st.expander("ℹ️ Wie funktioniert das Rollen? (Konzept)", expanded=False):
        st.markdown("""
**Warum rollen?**
Wenn dein Put im Verlust ist (der Kurs der Aktie ist unter deinen Strike gefallen),
kannst du den alten Put zurückkaufen und gleichzeitig einen neuen verkaufen —
idealerweise so, dass du netto noch Prämie einnimmst und deine Gewinnschwelle senkst.

**Die 3 Stufen (Buch Kap. 3):**
| Stufe | Was passiert | Ziel |
|-------|-------------|------|
| **1** | Niedrigerer Strike, gleiche Anzahl Kontrakte | GS senken, wenig Kapital |
| **2** | Gleicher Strike, gleiche Anzahl | GS senken wenn kein tieferer Strike möglich |
| **3** | Niedrigerer Strike, doppelte Kontrakte | GS maximal senken, mehr Kapital nötig |

**Ampel-Logik:**
- ✅ Netto-Prämie positiv UND neue Gewinnschwelle niedriger als alte
- ⚠️ Netto-Prämie positiv, aber GS wird nicht besser
- ❌ Roll kostet drauf (netto negativ) — kein sinnvoller Roll möglich

**Netto-Prämie** = Eröffnungsprämie + neue Prämie × Kontrakte − Rückkaufpreis
""")

    symbols = _load_symbols()
    if not symbols:
        st.error("Keine Symbole in der aktuellen Optionskette gefunden.")
        return

    col_sym, col_n = st.columns([2, 1])
    symbol = col_sym.selectbox("Symbol", symbols, index=None,
                               placeholder="Symbol wählen…", key="roll_symbol")
    n_contracts = col_n.number_input("Kontrakte (n)", min_value=1, value=1, step=1)

    if not symbol:
        st.info("Symbol wählen — erst dann werden Historie und Kurse geladen.")
        return

    # Reset "Puts laden"-State bei Symbol-/Datum-Wechsel
    prev_key = st.session_state.get("_roll_search_key")
    curr_key = str(symbol)
    if prev_key != curr_key:
        st.session_state["roll_puts_searched"] = False
        st.session_state["_roll_search_key"] = curr_key

    col_date, col_dte1, col_dte2 = st.columns([2, 1, 1])
    entry_date = col_date.date_input(
        "Einstiegsdatum (Eröffnung des Puts)",
        value=st.session_state.get("roll_entry_date_val", date.today()),
        max_value=date.today(),
        key="roll_entry_date_val",
        help="Wähle den Tag an dem du den Put verkauft hast.",
    )
    if not entry_date:
        return

    sc2, sc3 = col_dte1, col_dte2
    dte_min = sc2.number_input("DTE min", min_value=1, max_value=400,
                               value=st.session_state.get("roll_dte_min", 30), step=1,
                               key="roll_dte_min")
    dte_max = sc3.number_input("DTE max", min_value=1, max_value=400,
                               value=st.session_state.get("roll_dte_max", 60), step=1,
                               key="roll_dte_max")
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 2])
    show_monthly = fc1.checkbox("Monthly", value=True, key="roll_monthly")
    show_weekly  = fc2.checkbox("Weekly",  value=True, key="roll_weekly")
    show_daily   = fc3.checkbox("Daily",   value=False, key="roll_daily")
    with fc4:
        if st.button("🔍 Puts laden", key="roll_load_puts", type="primary"):
            st.session_state["roll_puts_searched"] = True
    if not st.session_state.get("roll_puts_searched"):
        st.info("Datum + DTE einstellen und 'Puts laden' klicken.")
        return

    with st.spinner("Lade Put-Historie…"):
        hist_df = _load_put_history(symbol, entry_date, dte_min, dte_max)
    if hist_df is None or hist_df.empty:
        st.warning(f"Keine Puts für {symbol} am {entry_date} im DTE-Bereich {dte_min}–{dte_max} gefunden.")
        return

    hist_df = filter_by_expiration_type(hist_df, "expiration_date",
                                        show_monthly, show_weekly, show_daily)
    if hist_df.empty:
        st.warning("Keine Puts für die gewählten Verfallstypen.")
        return

    hist_df = (hist_df
               .sort_values(["expiration_date", "strike_price"], ascending=[True, False])
               .reset_index(drop=True))

    exp_options = (hist_df[["expiration_date", "days_to_expiration"]]
                   .drop_duplicates()
                   .sort_values("expiration_date"))
    exp_labels = {}
    for _, e in exp_options.iterrows():
        exp = e["expiration_date"]
        dte = int(e["days_to_expiration"])
        typ = get_expiration_type(exp)
        exp_labels[f"{pd.to_datetime(exp).strftime('%d.%m.%Y')} · {dte} DTE · {typ}"] = exp

    st.markdown("**1. Verfallsdatum wählen:**")
    chosen_label = st.selectbox("Verfallsdatum", list(exp_labels.keys()),
                                index=None, placeholder="Verfall wählen…",
                                key="roll_expiry_pick", label_visibility="collapsed")
    if not chosen_label:
        st.info("Verfallsdatum wählen — dann erscheinen die Strikes.")
        return
    chosen_exp = exp_labels[chosen_label]

    exp_df = (hist_df[hist_df["expiration_date"] == chosen_exp]
              .sort_values("strike_price", ascending=True)
              .reset_index(drop=True))

    st.markdown("**2. Deinen Strike anklicken:**")

    if "roll_strike_selected_idx" not in st.session_state:
        st.session_state.roll_strike_selected_idx = None

    # Reset Strike-Auswahl wenn Verfall wechselt
    prev_exp = st.session_state.get("_roll_prev_exp")
    if prev_exp != str(chosen_exp):
        st.session_state.roll_strike_selected_idx = None
        st.session_state["_roll_prev_exp"] = str(chosen_exp)

    cols_per_row = 4
    num_strikes = len(exp_df)
    for row_idx in range((num_strikes + cols_per_row - 1) // cols_per_row):
        cols = st.columns(cols_per_row, gap="small")
        for col_idx, col in enumerate(cols):
            strike_idx = row_idx * cols_per_row + col_idx
            if strike_idx >= num_strikes:
                break
            sr = exp_df.iloc[strike_idx]
            strike  = float(sr["strike_price"])
            premium = float(sr["premium_option_price"])
            dte_val = int(sr["days_to_expiration"])
            is_sel  = strike_idx == st.session_state.roll_strike_selected_idx
            with col:
                if is_sel:
                    st.markdown(f"""
                    <div style="background:linear-gradient(135deg,rgba(0,112,74,0.4),rgba(0,212,170,0.25));
                        border:2px solid #00d4aa;border-radius:10px;padding:14px;
                        text-align:center;box-shadow:0 0 14px rgba(0,212,170,0.35);">
                        <div style="font-size:19px;font-weight:700;color:#00d4aa;font-family:'JetBrains Mono',monospace;">${strike:.2f}</div>
                        <div style="font-size:11px;color:#94a3b8;margin-top:4px;">Prämie ${premium:.2f}</div>
                        <div style="font-size:11px;color:#94a3b8;">DTE {dte_val}d</div>
                        <div style="font-size:10px;color:#00d4aa;margin-top:4px;font-weight:600;letter-spacing:0.08em;">✓ GEWÄHLT</div>
                    </div>""", unsafe_allow_html=True)
                else:
                    if st.button(
                        f"${strike:.2f}\n\n${premium:.2f} · {dte_val}d",
                        key=f"roll_strike_{strike_idx}",
                        use_container_width=True,
                    ):
                        st.session_state.roll_strike_selected_idx = strike_idx
                        st.rerun()

    selected_idx = st.session_state.roll_strike_selected_idx
    if selected_idx is None:
        st.info("👆 Strike-Kachel anklicken.")
        return
    put = exp_df.iloc[selected_idx]

    K = float(put["strike_price"])
    option_osi = put["option_osi"]
    expiration_date = put["expiration_date"]

    p_open_suggest = float(put["premium_option_price"])
    st.markdown("### 🛠️ Tatsächliche Ausführungskurse (Optional)")
    override = st.checkbox(
        "Echten Eröffnungs-Fill manuell eintragen",
        value=False,
        help="Ersetzt den historischen Tagesschluss durch deinen realen Verkaufspreis. "
             "Relevant wenn dein Fill deutlich vom day_close abwich.",
    )
    if override:
        p_open_suggest = st.number_input(
            "Eröffnungsprämie je Aktie ($)", min_value=0.0,
            value=p_open_suggest, step=0.01, format="%.2f",
            help="Was hast du beim Verkauf des Puts erhalten? (je Aktie, nicht je Kontrakt)",
        )
    P_eroeffnung = p_open_suggest * 100.0

    with ThreadPoolExecutor(max_workers=3) as ex:
        f_price = ex.submit(_current_put_price, option_osi, symbol)
        f_stock = ex.submit(_current_stock_price, symbol)
        p_today_share, price_src = f_price.result()
        S = f_stock.result()

    if p_today_share is None:
        st.error("Aktueller Put-Preis nicht ermittelbar.")
        return
    if S is None:
        st.error("Aktueller Aktienkurs nicht ermittelbar.")
        return
    P_heute = p_today_share * 100.0

    st.divider()
    st.markdown("### 📊 Aktuelle Position")
    pos = _render_position_card(symbol, K, S, p_today_share, P_eroeffnung, P_heute,
                                int(n_contracts), expiration_date, price_src)

    # Roll-Kandidaten
    st.divider()
    im_verlust = P_heute > P_eroeffnung
    if im_verlust:
        st.error("🔴 Position im Verlust — Rollen sinnvoll, um die Gewinnschwelle zu senken.")
    else:
        st.success("🟢 Position im Gewinn — Rollen optional (z. B. Laufzeit verlängern für mehr Prämie).")

    st.markdown("### 🎯 Roll-Kandidaten (alle 3 Stufen)")
    with st.expander("ℹ️ Wie lese ich die Tabelle?", expanded=False):
        st.markdown("""
- **Netto absolut**: Gesamtprämie nach dem Roll — positiv heißt du nimmst Geld ein
- **Neue GS**: Deine neue Gewinnschwelle nach dem Roll (je niedriger, desto besser)
- **Alte GS**: Deine aktuelle Gewinnschwelle (Vergleichswert)
- **Kapital nötig**: Cash der als Sicherheit hinterlegt werden muss (Strike × Kontrakte × 100)
- **Klick auf eine Zeile** → Plain-Language Erklärung was genau passiert
""")

    cand = _load_roll_candidates(symbol, K, 30, 90)
    if cand is None or cand.empty:
        st.warning("Keine aktuellen Put-Kandidaten (DTE 30–90, liquide) gefunden.")
        _render_endgame_hint()
        return

    cand = cand.copy()
    cand["premium_option_price"] = pd.to_numeric(cand["premium_option_price"], errors="coerce")
    cand["strike_price"] = pd.to_numeric(cand["strike_price"], errors="coerce")

    any_green = False
    breakeven_old = pos["breakeven_old"]

    st1 = cand[cand["strike_price"] < K]
    any_green |= _render_stufe(1, st1, K, P_eroeffnung, P_heute, int(n_contracts), breakeven_old,
                               "Stufe 1 — niedrigerer Basispreis, gleiche Kontrakte")

    st2 = cand[cand["strike_price"] == K]
    any_green |= _render_stufe(2, st2, K, P_eroeffnung, P_heute, int(n_contracts), breakeven_old,
                               "Stufe 2 — gleicher Basispreis, gleiche Kontrakte")

    st3 = cand[cand["strike_price"] < K]
    any_green |= _render_stufe(3, st3, K, P_eroeffnung, P_heute, 2 * int(n_contracts), breakeven_old,
                               "Stufe 3 — niedrigerer Basispreis, Kontrakte verdoppelt")

    if not any_green:
        _render_endgame_hint()


def _render_stufe(stufe, df, K, P_eroeffnung, P_heute, n, breakeven_old, title):
    """Roll-Kandidaten als horizontale Karten — Top-3 sofort sichtbar, Rest ausklappbar."""
    st.markdown(f"#### {title}")
    if df is None or df.empty:
        st.caption("Keine passenden Strikes in dieser Stufe.")
        return False

    df = df.sort_values(["expiration_date", "strike_price"],
                        ascending=[True, False]).reset_index(drop=True)

    # Alle Kandidaten vorberechnen
    candidates = []
    for i, (_, o) in enumerate(df.iterrows()):
        K2 = float(o["strike_price"])
        P_neu = float(o["premium_option_price"]) * 100.0
        r = roll_candidate(stufe=stufe, K=K, K2=K2, P_eroeffnung=P_eroeffnung,
                           P_heute=P_heute, P_neu=P_neu, n=n)
        candidates.append({"idx": i, "K2": K2, "P_neu": P_neu,
                            "expiry": o["expiration_date"],
                            "dte": int(o["days_to_expiration"]),
                            "oi": int(o["open_interest"]),
                            "vol": int(o["day_volume"]),
                            "result": r})

    # Sortieren: ✅ zuerst, dann nach Netto-Prämie
    ampel_rank = {"✅": 0, "⚠️": 1, "❌": 2}
    candidates.sort(key=lambda c: (ampel_rank.get(c["result"]["ampel"], 3), -c["result"]["netto_abs"]))

    any_green = any(c["result"]["ampel"] == "✅" for c in candidates)

    # Top-3 als Karten + "Alle anzeigen" Expander
    show_key = f"stufe_{stufe}_show_all"
    top3 = candidates[:3]
    rest = candidates[3:]

    _render_candidate_cards(top3, stufe, K, P_eroeffnung, P_heute, n, breakeven_old)

    if rest:
        with st.expander(f"Alle {len(candidates)} Kandidaten anzeigen"):
            _render_candidate_cards(rest, stufe, K, P_eroeffnung, P_heute, n, breakeven_old,
                                    key_offset=3)

    return any_green


def _render_candidate_cards(candidates, stufe, K, P_eroeffnung, P_heute, n, breakeven_old, key_offset=0):
    """Rendert Kandidaten als 3-spaltige Karten-Reihen mit Klick-Herleitung."""
    sel_key = f"stufe_{stufe}_sel"

    _AMPEL_BG = {"✅": ("rgba(0,212,170,0.12)", "#00d4aa"),
                 "⚠️": ("rgba(245,158,11,0.12)", "#f59e0b"),
                 "❌": ("rgba(239,68,68,0.10)", "#ef4444")}

    cols_per_row = 3
    for row_i in range(0, len(candidates), cols_per_row):
        chunk = candidates[row_i:row_i + cols_per_row]
        cols = st.columns(len(chunk), gap="small")
        for col, cand in zip(cols, chunk):
            r = cand["result"]
            bg, border = _AMPEL_BG.get(r["ampel"], ("rgba(30,45,69,0.6)", "#1e2d45"))
            gs_delta = breakeven_old - r["breakeven_new"]
            gs_arrow = f"▼ ${gs_delta:.2f}" if gs_delta > 0 else (f"▲ ${abs(gs_delta):.2f}" if gs_delta < 0 else "=")
            gs_color = "#00d4aa" if gs_delta > 0 else ("#ef4444" if gs_delta < 0 else "#64748b")
            netto_color = "#00d4aa" if r["netto_abs"] > 0 else "#ef4444"
            card_key = f"roll_cand_{stufe}_{cand['idx'] + key_offset}"
            is_sel = st.session_state.get(sel_key) == card_key

            with col:
                # Karte als HTML
                sel_border = "2px solid #00d4aa" if is_sel else f"1px solid {border}"
                sel_shadow = "box-shadow:0 0 16px rgba(0,212,170,0.35);" if is_sel else ""
                st.markdown(f"""
                <div style="background:{bg};border:{sel_border};border-radius:10px;
                    padding:14px 16px;margin-bottom:4px;{sel_shadow}">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:18px;
                        font-weight:700;color:#e2e8f0;">${cand['K2']:.2f}</span>
                    <span style="font-size:18px;">{r['ampel']}</span>
                  </div>
                  <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">
                    <div>
                      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;">Netto</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:13px;
                          font-weight:600;color:{netto_color};">${r['netto_abs']:+.2f}</div>
                    </div>
                    <div>
                      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;">GS-Delta</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:13px;
                          font-weight:600;color:{gs_color};">{gs_arrow}</div>
                    </div>
                    <div>
                      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;">DTE</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#94a3b8;">{cand['dte']}d</div>
                    </div>
                    <div>
                      <div style="font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#64748b;">Prämie</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#94a3b8;">${cand['P_neu']/100:.2f}</div>
                    </div>
                  </div>
                  <div style="font-size:9px;color:#475569;margin-top:8px;">
                    Neue GS: ${r['breakeven_new']:.2f} &nbsp;·&nbsp; OI {cand['oi']} / Vol {cand['vol']}
                  </div>
                </div>""", unsafe_allow_html=True)

                if st.button("Details →", key=card_key, use_container_width=True):
                    st.session_state[sel_key] = card_key
                    st.rerun()

    # Herleitung für ausgewählte Karte
    sel_card = st.session_state.get(sel_key)
    if sel_card:
        # Kandidat aus Key rekonstruieren
        try:
            parts = sel_card.split("_")
            sel_idx = int(parts[-1]) - key_offset
            if 0 <= sel_idx < len(candidates):
                cand = candidates[sel_idx]
                exp = roll_candidate_explained(stufe=stufe, K=K, K2=cand["K2"],
                                               P_eroeffnung=P_eroeffnung, P_heute=P_heute,
                                               P_neu=cand["P_neu"], n=n)
                _render_roll_explanation(exp, K, cand["K2"], P_eroeffnung, P_heute,
                                         cand["P_neu"], n, breakeven_old)
        except (ValueError, IndexError):
            pass


def _render_roll_explanation(exp: dict, K: float, K2: float, P_eroeffnung: float,
                             P_heute: float, P_neu: float, n: int, breakeven_old: float):
    """Plain-Language Roll-Erklärung statt Formel-Strings."""
    p_open_per_share = P_eroeffnung / 100
    p_today_per_share = P_heute / 100
    p_neu_per_share = P_neu / 100
    netto = exp["netto_abs"]
    netto_per_share = netto / (n * 100)
    gs_new = exp["breakeven_new"]
    gs_delta = breakeven_old - gs_new  # positiv = GS gesunken = gut
    ampel = exp["ampel"]

    with st.container(border=True):
        st.markdown(f"**{ampel} Was passiert bei diesem Roll?**")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Schritt 1 — Alten Put schließen:**")
            st.markdown(
                f"Du kaufst deinen bestehenden Put (Strike **${K:.2f}**) zurück. "
                f"Du hast ihn damals für **${p_open_per_share:.2f}** verkauft, "
                f"jetzt kostet er **${p_today_per_share:.2f}**. "
                + ("Das ist ein **Gewinn** für dich." if p_today_per_share < p_open_per_share
                   else "Das ist ein **Verlust** (Put ist teurer geworden).")
            )
        with col2:
            st.markdown(f"**Schritt 2 — Neuen Put eröffnen ({n}× Kontrakt{'e' if n > 1 else ''}):**")
            st.markdown(
                f"Du verkaufst {'je ' if n > 1 else ''}**{n}×** einen neuen Put "
                f"(Strike **${K2:.2f}**) und nimmst dafür **${p_neu_per_share:.2f}** je Aktie ein."
            )

        st.divider()

        if netto > 0:
            st.markdown(
                f"**Ergebnis:** Unterm Strich nimmst du **+${netto:.2f}** zusätzlich ein "
                f"(= ${netto_per_share:.2f} je Aktie × {n * 100} Aktien)."
            )
        else:
            st.markdown(
                f"**Ergebnis:** Dieser Roll **kostet dich ${abs(netto):.2f}** — "
                f"du musst draufzahlen. Kein sinnvoller Roll."
            )

        if gs_delta > 0:
            st.success(
                f"✅ Deine Gewinnschwelle sinkt von **${breakeven_old:.2f}** auf **${gs_new:.2f}** "
                f"(−${gs_delta:.2f}). Die Aktie darf nun weiter fallen, bevor du ins Minus gerätst."
            )
        elif gs_delta == 0:
            st.warning("⚠️ Gewinnschwelle bleibt gleich — Roll bringt keinen strukturellen Vorteil.")
        else:
            st.error(
                f"❌ Gewinnschwelle steigt von ${breakeven_old:.2f} auf ${gs_new:.2f} — "
                f"das ist schlechter als vorher."
            )

        st.caption(
            f"Kapital das als Sicherheit hinterlegt werden muss: **${exp['kapital_noetig']:.0f}** "
            f"(= ${K2:.2f} Strike × {n} × 100). "
            "🔶 Prämien = Tagesschluss (Näherung; echter Bid/Ask im Broker prüfen)."
        )


def _render_endgame_hint():
    st.info(
        "**Kein sinnvoller Put-Roll gefunden.** Nach Buchkonzept folgt jetzt das **Endspiel**: "
        "Aktien andienen lassen und Covered Calls schreiben (asymmetrische Technik: 1 Call auf 200 Aktien, "
        "Einstiegskurs über CC-Prämien bis zur Gewinnschwelle senken).\n\n"
        "→ Nutze dafür den **ITM Covered Call Scanner** (Seite in der Navigation)."
    )


# ---------------------------------------------------------------------------
# Tab 1 — Screener
# ---------------------------------------------------------------------------
@st.cache_data(ttl=300)
def _load_screener(dte_min, dte_max, min_oi, min_vol, price_min, price_max,
                   min_premium_share=0.0, min_market_cap=0):
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "put_screener.sql",
        params={"dte_min": int(dte_min), "dte_max": int(dte_max),
                "min_oi": int(min_oi), "min_vol": int(min_vol),
                "price_min": float(price_min), "price_max": float(price_max),
                "min_premium_share": float(min_premium_share),
                "min_market_cap": float(min_market_cap)},
    )


@st.cache_data(ttl=300)
def _load_symbol_puts(symbol, dte_min, dte_max, min_oi=100, min_vol=20, min_premium_share=0.0):
    return select_into_dataframe(
        sql_file_path=PATH_DATABASE_QUERY_FOLDER / "screener_symbol_puts.sql",
        params={"symbol": symbol, "dte_min": int(dte_min), "dte_max": int(dte_max),
                "min_oi": int(min_oi), "min_vol": int(min_vol),
                "min_premium_share": float(min_premium_share)},
    )


def render_screener_tab():
    st.subheader("📈 Screener — neuer Cash-Secured-Put-Einstieg")
    st.caption(
        "Qualifizierte Aktien nach Buch-Checkliste (Kap. 4+5) + Sektor-Kontext aus der RRG-Rotation. "
        "Harte Filter: Preis 15–80 $, OI/Vol ≥ 100. Kriterien mit '(aktuell)' sind Momentaufnahmen."
    )

    # Sektor-Quadrant-Map laden (im Hintergrund, kein Spinner)
    sector_map = _load_sector_quadrants()

    with st.expander("🔍 Filter", expanded=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        price_min, price_max = c1.slider("Aktienkurs ($)", 1, 500, (15, 80), 1)
        pe_max = c2.slider("KGV-Obergrenze", 10, 200, int(DEFAULT_PE_MAX), 5)
        min_score = c3.slider("Mindest-Score", 0, 9, 5, 1)
        dte_min, dte_max = c4.slider("DTE-Fenster (Tage)", 7, 90, (21, 45), 1)
        min_market_cap_b = c5.slider("Min. Market Cap (Mrd. $)", 0.0, 50.0, 2.0, 0.5,
                                     help="0 = kein Filter. Buch-Default: 2 Mrd. (keine Micro-Caps).")
        min_market_cap_usd = min_market_cap_b * 1e9 if min_market_cap_b > 0 else 0

        c6, c7, c8 = st.columns(3)
        min_oi = c6.number_input("Min. Open Interest", min_value=100, value=100, step=50)
        min_vol = c7.number_input("Min. Tagesvolumen", min_value=0, value=20, step=10)
        min_premium_contract = c8.number_input("Min. Prämie ($/Kontrakt)", min_value=0.0,
                                               value=50.0, step=10.0,
                                               help="50 $/Kontrakt = 0.50 $/Aktie.")
        min_premium_share = min_premium_contract / 100.0

        # Sektor-Filter (nur wenn Daten verfügbar)
        available_quadrants = sorted(set(sector_map.values())) if sector_map else []
        all_sectors = sorted(set(sector_map.keys())) if sector_map else []
        col_sq1, col_sq2 = st.columns(2)
        with col_sq1:
            sector_filter = st.multiselect(
                "Sektor-Filter",
                options=all_sectors,
                default=[],
                placeholder="Alle Sektoren",
                help="Nur Aktien aus diesen Sektoren anzeigen.",
            )
        with col_sq2:
            if available_quadrants:
                quadrant_filter = st.multiselect(
                    "RRG-Quadrant Filter",
                    options=available_quadrants,
                    default=[],
                    placeholder="Alle Quadranten",
                    help="Nur Aktien aus Sektoren mit diesem RRG-Status (aus der Sector-Rotation-Seite).",
                )
            else:
                quadrant_filter = []
                st.caption("⚪ Sektor-Rotation-Daten nicht verfügbar")

    if st.button("🔍 Screener starten", type="primary", key="run_screener"):
        st.session_state["screener_ran"] = True
    if not st.session_state.get("screener_ran"):
        st.info("Filter oben einstellen und 'Screener starten' klicken.")
        return

    with st.spinner("Screene Aktien + Puts …"):
        raw = _load_screener(dte_min, dte_max, min_oi, min_vol, price_min, price_max,
                             min_premium_share, min_market_cap_usd)

    if raw is None or raw.empty:
        st.warning("Keine Treffer. Filter lockern.")
        return

    scored = score_candidates(raw, pe_max=pe_max)
    scored = scored[scored["score"] >= min_score]
    if scored.empty:
        st.warning(f"Keine Aktie erreicht Score ≥ {min_score}.")
        return

    # Sektor-Ampel anfügen
    if sector_map:
        scored["sektor_quadrant"] = scored["sector"].map(sector_map).fillna("Unbekannt")
        scored["sektor_ampel"] = scored["sektor_quadrant"].map(_QUADRANT_EMOJI).fillna("⚪")
    else:
        scored["sektor_quadrant"] = "Unbekannt"
        scored["sektor_ampel"] = "⚪"

    # Sektor-Filter anwenden
    if sector_filter:
        scored = scored[scored["sector"].isin(sector_filter)]
    if quadrant_filter:
        scored = scored[scored["sektor_quadrant"].isin(quadrant_filter)]

    if scored.empty:
        st.warning("Keine Treffer nach Sektor-/Quadrant-Filter.")
        return

    display_cols = [
        "sektor_ampel", "symbol", "price", "score",
        "put_strike", "put_expiry", "put_dte", "put_premium",
        "premium_pct", "annualized_pct", "breakeven", "capital_required",
        "sector",
    ]
    display_cols = [c for c in display_cols if c in scored.columns]

    st.success(f"{len(scored)} qualifizierte Aktien (Score ≥ {min_score}).")
    if sector_map:
        legend_parts = [f"{_QUADRANT_EMOJI[q]} {q}" for q in ["Leading", "Improving", "Weakening", "Lagging"]]
        st.caption("Sektor-Ampel: " + "  ·  ".join(legend_parts))

    sel_key = "screener_selected_symbol"

    # Cards: 4 pro Zeile, bewusst reduziert auf 3 Kernwerte + Score + Sektor
    cols_per_row = 4
    for row_i in range(0, len(scored), cols_per_row):
        chunk = scored.iloc[row_i:row_i + cols_per_row]
        cols = st.columns(len(chunk), gap="small")
        for col, (_, r) in zip(cols, chunk.iterrows()):
            sym          = r["symbol"]
            score_val    = int(r["score"])
            score_max_v  = int(r["score_max"])
            ann_val      = float(r.get("annualized_pct") or 0)
            put_dte      = r.get("put_dte", "—")
            put_strike   = r.get("put_strike", "—")
            sector_v     = r.get("sector", "")
            quadrant_v   = r.get("sektor_quadrant", "Unbekannt")
            ampel_v      = _QUADRANT_EMOJI.get(quadrant_v, "⚪")
            qcolor       = _QUADRANT_COLOR.get(quadrant_v, "#64748b")
            score_pct    = score_val / score_max_v * 100 if score_max_v else 0
            # Score-Farbe: klar lesbar auf hellem Kartengrund
            score_color  = "#059669" if score_pct >= 70 else ("#d97706" if score_pct >= 50 else "#dc2626")
            is_sel       = st.session_state.get(sel_key) == sym

            # Heller Kartengrund (#1e293b = schieferblau) statt fast-schwarz
            bg       = "#162032" if not is_sel else "#0f2a1e"
            border   = "2px solid #00d4aa" if is_sel else "1px solid #2d3f55"

            with col:
                st.markdown(f"""
                <div style="background:{bg};border:{border};border-radius:10px;
                    padding:14px 14px 10px;margin-bottom:2px;">

                  <!-- Zeile 1: Symbol links, Score rechts -->
                  <div style="display:flex;justify-content:space-between;
                      align-items:baseline;margin-bottom:10px;">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:17px;
                        font-weight:700;color:#f1f5f9;letter-spacing:.03em;">{sym}</span>
                    <span style="font-size:11px;font-weight:600;
                        color:{score_color};background:{score_color}1a;
                        border:1px solid {score_color}55;border-radius:5px;
                        padding:1px 7px;">{score_val}/{score_max_v}</span>
                  </div>

                  <!-- Zeile 2: 3 Kennzahlen -->
                  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;
                      gap:0;margin-bottom:10px;">
                    <div style="border-right:1px solid #2d3f55;padding-right:8px;">
                      <div style="font-size:9px;color:#7c93ad;text-transform:uppercase;
                          letter-spacing:.07em;margin-bottom:2px;">Ann.%</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:15px;
                          font-weight:700;color:#34d399;">{ann_val:.1f}%</div>
                    </div>
                    <div style="border-right:1px solid #2d3f55;padding:0 8px;">
                      <div style="font-size:9px;color:#7c93ad;text-transform:uppercase;
                          letter-spacing:.07em;margin-bottom:2px;">Strike</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:15px;
                          font-weight:600;color:#cbd5e1;">${put_strike}</div>
                    </div>
                    <div style="padding-left:8px;">
                      <div style="font-size:9px;color:#7c93ad;text-transform:uppercase;
                          letter-spacing:.07em;margin-bottom:2px;">DTE</div>
                      <div style="font-family:'JetBrains Mono',monospace;font-size:15px;
                          font-weight:600;color:#cbd5e1;">{put_dte}d</div>
                    </div>
                  </div>

                  <!-- Zeile 3: Sektor-Badge -->
                  <div style="font-size:10px;color:{qcolor};opacity:.85;">
                    {ampel_v} {sector_v or "—"}
                  </div>
                </div>""", unsafe_allow_html=True)

                btn_label = "✓ Gewählt" if is_sel else "→"
                if st.button(btn_label, key=f"screener_card_{sym}", use_container_width=True):
                    st.session_state[sel_key] = sym
                    st.rerun()

    # Ausgewählte Aktie ermitteln
    sel_sym = st.session_state.get(sel_key)
    if not sel_sym or sel_sym not in scored["symbol"].values:
        st.info("Karte anklicken für Details.")
        return

    row = scored[scored["symbol"] == sel_sym].iloc[0]
    sector_en = row.get("sector", "")
    quadrant = sector_map.get(sector_en, "Unbekannt")

    st.divider()

    # Header mit Symbol + Sektor-Badge + Vollanalyse-Button
    h1, h2 = st.columns([3, 1])
    with h1:
        st.markdown(f"### 🔬 {row['symbol']}  ({int(row['score'])}/{int(row['score_max'])} Punkte)")
        if sector_en:
            st.markdown(_sector_badge_html(sector_en, quadrant), unsafe_allow_html=True)
            if quadrant in ("Leading", "Improving"):
                st.caption(f"✅ Sektor **{sector_en}** ist aktuell im RRG-Quadrant **{quadrant}** — tendenziell günstiger Zeitpunkt.")
            elif quadrant == "Weakening":
                st.caption(f"⚠️ Sektor **{sector_en}** ist im Quadrant **Weakening** — Momentum dreht ab, erhöhte Vorsicht.")
            elif quadrant == "Lagging":
                st.caption(f"🔴 Sektor **{sector_en}** ist im Quadrant **Lagging** — relativer Stärke-Nachteil.")
    with h2:
        st.markdown("")
        st.markdown("")
        if st.button(f"🔗 Vollanalyse {row['symbol']}", key="goto_symbol", type="secondary"):
            st.session_state["symbol_page_symbol"] = row["symbol"]
            st.switch_page("pages/symbolpage.py")

    # Score-Herleitung
    bd = score_breakdown(row, pe_max=pe_max)
    ann_map = {"aktuell": "🔶 (aktuell)", "Näherung": "🔶 (Näherung)", "day_close": "🔶 (day_close)", "": ""}
    detail = pd.DataFrame([{
        "Kriterium": i["label"],
        "Erreicht": "✅" if i["erreicht"] else "❌",
        "Möglich": i["moeglich"],
        "Ist-Wert": i["ist_wert"],
        "Annahme": ann_map.get(i["annahme"], ""),
    } for i in bd])
    st.dataframe(detail, use_container_width=True, hide_index=True)

    getroffene = sorted({i["annahme"] for i in bd if i["annahme"]})
    if getroffene:
        with st.expander("⚠️ Getroffene Annahmen", expanded=False):
            texte = {
                "aktuell": "**(aktuell):** Momentaufnahme statt Mehrjahres-Trend.",
                "Näherung": "**(Näherung):** Ersatzgröße statt echtem Wert (z. B. Support ≈ 52W-Tief + SMA200).",
                "day_close": "**(day_close):** Prämie = Tagesschluss statt echtem Bid/Ask.",
            }
            for a in getroffene:
                st.markdown("- " + texte.get(a, a))

    # IV-Rank Chart
    st.divider()
    st.markdown(f"### 📊 IV-Rank Verlauf — {row['symbol']}")
    with st.expander("ℹ️ Was zeigt dieser Chart?", expanded=False):
        st.markdown("""
Der Chart zeigt den **IV-Rank** der letzten ~12 Monate.

- **IV-Rank** = Wo liegt die aktuelle IV im Vergleich zum Jahres-Hoch/Tief? 0 = historisches Tief, 100 = historisches Hoch.
- **Rote Zone (P75+)** = IV historisch hoch → Prämien sind überdurchschnittlich hoch → guter Zeitpunkt für Prämienverkäufer.
- **Grüne Zone (P25−)** = IV niedrig → Prämien eher mager → schlechterer Zeitpunkt für CSP.
- **IV-Percentile** (gestrichelt) = Wie viele der letzten Tage hatte eine niedrigere IV? Ähnlich wie IV-Rank, aber robuster bei Ausreißern.
""")
    _render_iv_chart(row["symbol"])

    # Verkaufbare Puts
    st.divider()
    st.markdown("### Verkaufbare Puts — jetzt")
    pc1, pc2, _pc3 = st.columns([1, 1, 2])
    p_dte_min, p_dte_max = pc1.slider("DTE-Fenster", 7, 90, (30, 45), 1, key="screener_put_dte")
    min_puffer = pc2.slider("Min. Puffer % (für ✅)", 0, 30, int(DEFAULT_MIN_PUFFER_PCT), 1,
                            key="screener_min_puffer",
                            help="Abstand Aktienkurs → Strike, ab dem ein Put grün wird.")
    with st.expander("ℹ️ Wie wird bewertet?", expanded=False):
        st.markdown(
            f"- **✅** = annualisierte Rendite ≥ **12 %** UND Puffer ≥ **{min_puffer} %** UND Prämie über Black-Scholes-Preis.\n"
            f"- **⚠️** = Rendite ≥ 12 %, aber Puffer oder BS-Edge nicht erfüllt.\n"
            f"- **❌** = annualisierte Rendite < 12 %.\n"
            f"- **Puffer** = wie weit die Aktie fallen darf, bis sie den Strike erreicht.\n"
            f"- **BS-Preis grün** = Markt-Prämie > Black-Scholes-Preis → gut für Verkäufer."
        )
    puts = _load_symbol_puts(row["symbol"], p_dte_min, p_dte_max,
                             min_oi=min_oi, min_vol=min_vol, min_premium_share=min_premium_share)
    if puts is None or puts.empty:
        st.info(f"Keine liquiden Puts für {row['symbol']} im DTE-Fenster {p_dte_min}–{p_dte_max}.")
    else:
        def _num(v):
            return float(v) if v is not None and pd.notna(v) else None

        def _bs_put(S, K, iv, dte):
            S, K, iv = _num(S), _num(K), _num(iv)
            dte = int(dte) if dte is not None and pd.notna(dte) else 0
            if not S or not K or not iv or iv <= 0 or dte <= 0:
                return None
            try:
                return round(PutValue(S, K, iv, dte, RISK_FREE_RATE), 2)
            except (ValueError, ZeroDivisionError):
                return None

        put_rows = []
        for _, o in puts.iterrows():
            m = put_metrics(o["strike_price"], o["premium_option_price"], o["days_to_expiration"])
            iv = _num(o["implied_volatility"])
            bs = _bs_put(o["live_stock_price"], o["strike_price"], iv, o["days_to_expiration"])
            delta, theta = _num(o["greeks_delta"]), _num(o["greeks_theta"])
            exp_move = _num(o.get("expected_move"))
            ev = put_evaluation(kurs=o["live_stock_price"], strike=o["strike_price"],
                                praemie=o["premium_option_price"], dte=o["days_to_expiration"],
                                iv=iv, delta=delta, bs_preis=bs, min_puffer_pct=min_puffer)
            put_rows.append({
                "Ampel": ev["ampel"],
                "Expiry": o["expiration_date"],
                "Strike": round(float(o["strike_price"]), 2),
                "DTE": int(o["days_to_expiration"]),
                "Prämie ($)": round(float(o["premium_option_price"]), 2),
                "BS-Preis ($)": bs,
                "Rendite %": round(m["premium_pct"], 2),
                "Annualisiert %": round(m["annualized_pct"], 1),
                "Puffer %": round(ev["puffer_pct"], 1),
                "Prob. Zuw. %": round(ev["prob_assignment_pct"], 1) if ev["prob_assignment_pct"] is not None else None,
                "Gewinnschwelle": round(m["breakeven"], 2),
                "Kapital ($)": round(m["capital_required"], 0),
                "Delta": round(delta, 3) if delta is not None else None,
                "Theta": round(theta, 4) if theta is not None else None,
                "IV %": round(iv * 100, 1) if iv is not None else None,
                "Exp. Move": round(exp_move, 2) if exp_move is not None else None,
                "OI": int(o["open_interest"]),
                "Vol": int(o["day_volume"]),
            })

        ampel_rank = {"✅": 0, "⚠️": 1, "❌": 2}
        put_df = pd.DataFrame(put_rows)
        put_df["_a"] = put_df["Ampel"].map(ampel_rank).fillna(3)
        put_df = (put_df.sort_values(["_a", "Annualisiert %"], ascending=[True, False])
                  .drop(columns=["_a"]).reset_index(drop=True))

        def _highlight_bs(r):
            styles = [""] * len(r)
            bs_v, pr_v = r.get("BS-Preis ($)"), r.get("Prämie ($)")
            if bs_v is not None and pd.notna(bs_v) and pr_v is not None and pd.notna(pr_v):
                col = "#90EE90" if float(pr_v) > float(bs_v) else "#FFB6B6"
                idx = put_df.columns.get_loc("BS-Preis ($)")
                styles[idx] = f"background-color: {col}; color: #000000; font-weight: bold"
            return styles

        put_event = st.dataframe(put_df.style.apply(_highlight_bs, axis=1),
                                 use_container_width=True, hide_index=True,
                                 on_select="rerun", selection_mode="single-row",
                                 key="screener_put_pick")
        st.caption(
            "🔶 Prämie = day_close (Näherung). "
            "BS-Preis grün = Markt teurer als Black-Scholes. "
            "Sortiert: ✅ oben, dann höchste annualisierte Rendite. **Klick für Details.**"
        )

        psel = put_event.selection.rows if hasattr(put_event, "selection") else []
        if psel:
            p = put_df.iloc[psel[0]]
            st.markdown(f"#### {p['Ampel']} Put-Detail — {row['symbol']} {p['Strike']:.2f} · {p['Expiry']}")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Prämie", f"${p['Prämie ($)']:.2f}",
                      help="Markt-Prämie (day_close) je Aktie. Kontrakt = ×100.")
            bs_txt = f"${p['BS-Preis ($)']:.2f}" if pd.notna(p["BS-Preis ($)"]) else "—"
            bs_help = ("Black-Scholes Put-Preis: fairer theoretischer Wert basierend auf S, K, IV, DTE, r. "
                       "Markt > BS = Prämie ist 'teuer' → gut für Verkäufer.")
            if pd.notna(p["BS-Preis ($)"]):
                bs_help += f" Aktuell: {'über BS ✅' if p['Prämie ($)'] > p['BS-Preis ($)'] else 'unter BS ⚠️'}"
            d1.metric("BS-Preis", bs_txt, help=bs_help)
            d2.metric("Rendite", f"{p['Rendite %']:.2f}%",
                      help="Prämie / Strike × 100. Zeigt wie viel % des eingesetzten Kapitals die Prämie ausmacht.")
            d2.metric("Annualisiert", f"{p['Annualisiert %']:.1f}%",
                      help="Rendite % × (365 / DTE). Vergleichbar mit Jahreszins — normiert auf 1 Jahr.")
            d3.metric("Puffer bis Strike", f"{p['Puffer %']:.1f}%",
                      help="(Kurs − Strike) / Kurs × 100. Wie weit darf die Aktie fallen bevor du angedient wirst?")
            prob_txt = f"{p['Prob. Zuw. %']:.1f}%" if pd.notna(p["Prob. Zuw. %"]) else "—"
            d3.metric("Prob. Zuweisung", prob_txt,
                      help="Black-Scholes N(−d2): Wahrscheinlichkeit dass der Kurs bei Verfall UNTER dem Strike liegt. "
                           "Fallback: |Delta| wenn IV fehlt. Je niedriger, desto sicherer.")
            d4.metric("DTE", f"{int(p['DTE'])} T",
                      help="Days to Expiration — verbleibende Tage bis zum Verfallstag.")
            d4.metric("Delta", f"{p['Delta']:.3f}" if pd.notna(p["Delta"]) else "—",
                      help="Sensitivität des Put-Preises auf ±1$ Kursbewegung. "
                           "Delta −0.30 = Put steigt ~0.30$ wenn Aktie 1$ fällt. "
                           "Betrag ≈ grobe Zuweis.-Wahrscheinlichkeit.")
            g1, g2, g3, g4 = st.columns(4)
            g1.metric("Gewinnschwelle", f"${p['Gewinnschwelle']:.2f}",
                      help="Strike − Prämie. Unterhalb dieser Schwelle verlierst du Geld bei Andienung.")
            g1.metric("Kapital (CSP)", f"${p['Kapital ($)']:.0f}",
                      help="Strike × 100. Cash der als Sicherheit geblockt wird (Cash-Secured Put).")
            g2.metric("Theta", f"{p['Theta']:.4f}" if pd.notna(p["Theta"]) else "—",
                      help="Zeitwertverlust pro Tag in $. Als Verkäufer ist positives Theta dein Freund — "
                           "der Put verliert täglich an Wert auch ohne Kursbewegung.")
            g2.metric("IV", f"{p['IV %']:.1f}%" if pd.notna(p["IV %"]) else "—",
                      help="Implizite Volatilität: die vom Markt eingepreiste erwartete Schwankungsbreite (annualisiert). "
                           "Hohe IV = höhere Prämien, aber auch höheres Risiko.")
            g3.metric("Exp. Move", f"±{p['Exp. Move']:.2f}" if pd.notna(p["Exp. Move"]) else "—",
                      help="Expected Move: erwartete Kursbewegung bis Verfall (±1σ). "
                           "Berechnung: Kurs × IV × √(DTE/365). "
                           "68% Wahrscheinlichkeit dass der Kurs innerhalb dieser Spanne bleibt.")
            g4.metric("OI / Vol", f"{int(p['OI'])} / {int(p['Vol'])}",
                      help="Open Interest: offene Kontrakte (Liquiditäts-Indikator). "
                           "Tagesvolumen: heute gehandelte Kontrakte. "
                           "Beide sollten > 100 sein für faire Bid/Ask-Spreads.")


# ---------------------------------------------------------------------------
# Seite
# ---------------------------------------------------------------------------
_inject_css()

tab_screener, tab_roller = st.tabs(["📈 Screener (Neuer Einstieg)", "🔄 Roller (Rollen)"])
with tab_screener:
    render_screener_tab()
with tab_roller:
    render_roller_tab()
