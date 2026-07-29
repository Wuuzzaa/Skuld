"""
ITM Covered Call Scanner
========================
Scans for optimal In-The-Money (ITM) Covered Call opportunities, mirroring
the PowerOptions MorningUpdate newsletter format.

Strategy Overview
-----------------
A Covered Call means: buy 100 shares + sell 1 call option against them.
An ITM Covered Call uses a strike BELOW the current stock price.

Why ITM instead of OTM?
- The premium is larger (call has intrinsic value)
- Higher downside protection (you are protected by the full premium)
- Lower upside: if the stock stays above the strike, shares get called away
- Best for: conservative income, protecting existing positions

Core Metrics (PowerOptions style)
----------------------------------
Net Debit          = Stock Price - Premium received
                     → Your actual cost basis for the position

Assigned Return    = (Strike - Net Debit) / Net Debit × 100
                     → Profit % if shares get called away at expiry

Annualized Return  = Assigned Return / DTE × 365
                     → Normalized return for comparison across expirations

Downside Protection = Premium / Stock Price × 100
                     → How far the stock can fall before you lose money

DTE Selection
-------------
Sweet spot: 21–45 days to expiration.
- Below 21 DTE: premium too small, little time to manage
- 21–30 DTE: maximum theta decay, ideal for active traders
- 30–45 DTE: more premium, more buffer, better for conservative approach
- Above 45 DTE: capital tied up too long, theta decay too slow

Delta as a selector
-------------------
Delta ~0.7–0.8: moderate ITM, good balance of premium and assignment risk
Delta ~0.8–0.9: deeper ITM, more protection, lower return
Delta ~0.6–0.7: slightly less ITM, more upside potential
"""

import logging
import os
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.sector_rotation import (
    RotationParameters, load_sector_rotation_price_history,
    calculate_sector_rotation, build_latest_sector_snapshot,
)

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# ── Quadrant-Helpers (identisch Roll & Screen) ────────────────────────────────
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


@st.cache_data(ttl=300)
def _load_iv_history(symbol: str) -> pd.DataFrame | None:
    return select_into_dataframe(
        query="""
            SELECT date, symbol,
                   ROUND(iv::numeric * 100, 2)       AS iv,
                   ROUND(iv_rank::numeric, 2)          AS iv_rank,
                   ROUND(iv_percentile::numeric, 2)    AS iv_percentile
            FROM "StockImpliedVolatilityMassiveHistory"
            WHERE symbol = :symbol
              AND date >= CURRENT_DATE - INTERVAL '365 days'
              AND date <= CURRENT_DATE
            ORDER BY date ASC
        """,
        params={"symbol": symbol},
    )


def _render_iv_chart(symbol: str):
    iv_df = _load_iv_history(symbol)
    if iv_df is None or iv_df.empty:
        st.caption("Keine IV-Rank-Historie verfügbar.")
        return

    iv_df = iv_df.sort_values("date")
    iv_df["date"] = pd.to_datetime(iv_df["date"])

    iv_vals = iv_df["iv_rank"].dropna()
    p25 = iv_vals.quantile(0.25)
    p50 = iv_vals.quantile(0.50)
    p75 = iv_vals.quantile(0.75)

    _theme_base = st.get_option("theme.base")
    _theme_bg   = st.get_option("theme.backgroundColor") or ""
    if _theme_base == "light":
        _dark = False
    elif _theme_base == "dark":
        _dark = True
    else:
        _bg = _theme_bg.lstrip("#")
        _dark = True
        if len(_bg) == 6:
            try:
                r, g, b = int(_bg[0:2], 16), int(_bg[2:4], 16), int(_bg[4:6], 16)
                _dark = (0.299 * r + 0.587 * g + 0.114 * b) < 128
            except ValueError:
                pass

    _paper = "#1a1a2e" if _dark else "#ffffff"
    _plot  = "#16213e" if _dark else "#f8fafc"
    _text  = "#e2e8f0" if _dark else "#1e293b"
    _grid  = "rgba(255,255,255,0.08)" if _dark else "rgba(0,0,0,0.06)"

    fig = go.Figure()

    # Bänder
    fig.add_hrect(y0=60, y1=100, fillcolor="rgba(34,197,94,0.08)", line_width=0,
                  annotation_text="Teuer (gut zum Verkaufen)", annotation_position="top left",
                  annotation_font_size=10, annotation_font_color="#22c55e")
    fig.add_hrect(y0=0, y1=40, fillcolor="rgba(239,68,68,0.06)", line_width=0,
                  annotation_text="Günstig (dünne Prämie)", annotation_position="bottom left",
                  annotation_font_size=10, annotation_font_color="#ef4444")

    # Perzentil-Linien
    for pval, label, color in [(p25, "P25", "#64748b"), (p50, "Median", "#94a3b8"), (p75, "P75", "#64748b")]:
        fig.add_hline(y=pval, line_dash="dot", line_color=color, line_width=1,
                      annotation_text=f"{label} {pval:.0f}%", annotation_position="right",
                      annotation_font_size=9)

    # IV-Rank-Linie
    fig.add_trace(go.Scatter(
        x=iv_df["date"], y=iv_df["iv_rank"],
        mode="lines",
        name="IV Rank",
        line=dict(color="#f59e0b", width=2),
        fill="tozeroy",
        fillcolor="rgba(245,158,11,0.10)",
        hovertemplate="%{x|%d.%m.%Y}<br>IV Rank: %{y:.0f}%<extra></extra>",
    ))

    # IV (reine %-Linie, sekundäre Y-Achse)
    if "iv" in iv_df.columns:
        fig.add_trace(go.Scatter(
            x=iv_df["date"], y=iv_df["iv"],
            mode="lines",
            name="IV %",
            line=dict(color="#818cf8", width=1.5, dash="dot"),
            yaxis="y2",
            hovertemplate="%{x|%d.%m.%Y}<br>IV: %{y:.1f}%<extra></extra>",
        ))

    fig.update_layout(
        height=260,
        margin=dict(l=0, r=60, t=8, b=0),
        paper_bgcolor=_paper,
        plot_bgcolor=_plot,
        font=dict(color=_text, size=11),
        legend=dict(orientation="h", y=1.08, x=0, font_size=10),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(title="IV Rank %", range=[0, 105], gridcolor=_grid, zeroline=False),
        yaxis2=dict(title="IV %", overlaying="y", side="right",
                    showgrid=False, zeroline=False, range=[0, 150]),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_payoff_chart(stock: float, strike: float, premium: float,
                          net_debit: float, dte: int):
    """Payoff-Diagramm für ITM Covered Call am Verfall."""
    _theme_base = st.get_option("theme.base")
    _dark = _theme_base != "light"
    _paper = "#1a1a2e" if _dark else "#ffffff"
    _plot  = "#16213e" if _dark else "#f8fafc"
    _text  = "#e2e8f0" if _dark else "#1e293b"
    _grid  = "rgba(255,255,255,0.08)" if _dark else "rgba(0,0,0,0.06)"

    lo = net_debit * 0.70
    hi = stock * 1.15
    prices = np.linspace(lo, hi, 300)

    # ITM Covered Call P&L: max profit cap at strike, loss below breakeven
    pnl = np.where(
        prices >= strike,
        (strike - net_debit) * 100,          # capped upside
        (prices - net_debit) * 100            # loss zone
    )

    breakeven = net_debit
    max_profit = (strike - net_debit) * 100

    fig = go.Figure()

    # Profit zone fill
    fig.add_trace(go.Scatter(
        x=prices, y=np.maximum(pnl, 0),
        fill="tozeroy", fillcolor="rgba(34,197,94,0.12)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    # Loss zone fill
    fig.add_trace(go.Scatter(
        x=prices, y=np.minimum(pnl, 0),
        fill="tozeroy", fillcolor="rgba(239,68,68,0.12)",
        line=dict(width=0), showlegend=False, hoverinfo="skip",
    ))
    # P&L line
    fig.add_trace(go.Scatter(
        x=prices, y=pnl,
        mode="lines",
        name="P&L",
        line=dict(color="#22c55e", width=2.5),
        hovertemplate="Kurs: $%{x:.2f}<br>P&L: $%{y:.0f}<extra></extra>",
    ))

    # Vertikale Linien
    for x, label, color in [
        (breakeven, f"Breakeven ${breakeven:.2f}", "#ef4444"),
        (strike,    f"Strike ${strike:.2f}",        "#f59e0b"),
        (stock,     f"Kurs ${stock:.2f}",            "#818cf8"),
    ]:
        fig.add_vline(x=x, line_dash="dash", line_color=color, line_width=1.5,
                      annotation_text=label, annotation_position="top",
                      annotation_font_size=10, annotation_font_color=color)

    # Max-Profit-Linie
    fig.add_hline(y=max_profit, line_dash="dot", line_color="#22c55e", line_width=1,
                  annotation_text=f"Max +${max_profit:.0f}", annotation_position="right",
                  annotation_font_size=10, annotation_font_color="#22c55e")
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)

    fig.update_layout(
        height=280,
        margin=dict(l=0, r=60, t=8, b=0),
        paper_bgcolor=_paper,
        plot_bgcolor=_plot,
        font=dict(color=_text, size=11),
        xaxis=dict(title="Aktienkurs bei Verfall ($)", gridcolor=_grid, zeroline=False),
        yaxis=dict(title="P&L pro Kontrakt ($)", gridcolor=_grid, zeroline=False),
        hovermode="x unified",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ── Page header ───────────────────────────────────────────────────────────────
st.title("ITM Covered Call Scanner")
st.caption(
    "Find optimal In-The-Money Covered Calls ranked by annualized return — "
    "PowerOptions MorningUpdate style."
)

with st.expander("How ITM Covered Calls work", expanded=False):
    st.markdown("""
    **The trade**
    Buy 100 shares + sell 1 ITM call (strike below current price).

    **Why ITM?**
    The premium is larger because the call has intrinsic value.
    This gives you more downside protection at the cost of capping your upside.

    **The four key metrics**

    | Metric | Formula | Meaning |
    |--------|---------|---------|
    | Net Debit | Stock Price − Premium | Your real cost basis |
    | Assigned Return | (Strike − Net Debit) / Net Debit | Profit if called away |
    | Annualized Return | Assigned Return / DTE × 365 | Comparable across expirations |
    | Downside Protection | Premium / Stock Price | Buffer before losing money |

    **Example (ERO from PowerOptions newsletter)**
    - Stock: $30.44 | Call Strike: $25.00 | Premium: $5.75 | DTE: 29
    - Net Debit: $24.69 | Assigned Return: 1.3% | Annualized: 15.9% | Protection: 18.9%

    **DTE Sweet Spot: 21–45 days**
    Theta decay accelerates in this zone. Close at 50% profit and redeploy.

    **Earnings filter**
    Always exclude positions where earnings fall before expiry —
    IV crush after earnings destroys the premium edge.
    """)

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("cc_df", None),
    ("cc_selected_idx", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sektor-Quadranten laden ───────────────────────────────────────────────────
sector_quadrants = _load_sector_quadrants()   # {sector_en: quadrant}
all_quadrants = ["Leading", "Improving", "Weakening", "Lagging"]
available_quadrants = sorted({q for q in sector_quadrants.values() if q in all_quadrants})
all_sectors_with_quadrant = sorted(sector_quadrants.keys())

# ── Filter controls ───────────────────────────────────────────────────────────
st.subheader("Scanner Filters")

# --- Gruppe 1: Laufzeit & Delta ---
with st.container():
    st.markdown("##### Laufzeit & Delta")
    col1, col2, col3 = st.columns(3)
    with col1:
        dte_min, dte_max = st.slider(
            "DTE Range (days to expiration)",
            min_value=7, max_value=90,
            value=(21, 45), step=1,
            key="cc_dte",
            help="Sweet spot: 21–45 days. Theta decay is fastest here.",
        )
    with col2:
        delta_target = st.slider(
            "Delta Target",
            min_value=0.50, max_value=0.95,
            value=0.80, step=0.05,
            key="cc_delta",
            help="0.8 = deep ITM, more protection. 0.6 = slightly ITM, more upside.",
        )
    with col3:
        delta_target_max = st.slider(
            "Max Delta",
            min_value=0.70, max_value=0.99,
            value=0.90, step=0.01,
            key="cc_max_delta_top",
            help="Exclude extremely deep ITM calls. Above 0.90 the assigned return becomes unstable.",
        )

st.markdown("---")

# --- Gruppe 2: Rendite & Schutz ---
with st.container():
    st.markdown("##### Rendite & Schutz")
    col4, col5, col6 = st.columns(3)
    with col4:
        min_annualized = st.number_input(
            "Min Annualized Return %",
            min_value=0, max_value=200,
            value=10, step=5,
            key="cc_min_ann",
            help="Untergrenze der annualisierten Rendite.",
        )
    with col5:
        max_annualized = st.number_input(
            "Max Annualized Return %",
            min_value=10, max_value=1000,
            value=30, step=10,
            key="cc_max_ann",
            help="Cap utopian values. Above ~100% is usually a data artefact or illiquid option.",
        )
    with col6:
        min_downside = st.slider(
            "Min Downside Protection %",
            min_value=0, max_value=40,
            value=10, step=1,
            key="cc_min_downside",
            help="Filter out positions with insufficient downside buffer.",
        )

st.markdown("---")

# --- Gruppe 3: Aktie & Liquidität ---
with st.container():
    st.markdown("##### Aktie & Liquidität")
    col7, col8, col9 = st.columns(3)
    with col7:
        price_min = st.number_input(
            "Min Stock Price ($)",
            min_value=0.0, max_value=10000.0,
            value=0.0, step=5.0, format="%.0f",
            key="cc_price_min",
            help="0 = keine Untergrenze.",
        )
    with col8:
        price_max = st.number_input(
            "Max Stock Price ($)",
            min_value=0.0, max_value=10000.0,
            value=0.0, step=5.0, format="%.0f",
            key="cc_price_max",
            help="0 = keine Obergrenze.",
        )
    with col9:
        min_market_cap_b = st.number_input(
            "Min Market Cap ($B)",
            min_value=0.0, max_value=50.0,
            value=1.0, step=0.5,
            format="%.1f",
            key="cc_min_cap",
        )

    col10, col11, col12 = st.columns(3)
    with col10:
        min_oi = st.number_input(
            "Min Open Interest",
            min_value=0, max_value=1000,
            value=50, step=25,
            key="cc_min_oi",
        )
    with col11:
        min_iv_rank = st.number_input(
            "Min IV Rank",
            min_value=0, max_value=100,
            value=50, step=5,
            key="cc_min_iv_rank",
            help="PowerOptions: IV Rank >= 50 ensures options are expensive enough to sell.",
        )
    with col12:
        min_premium = st.number_input(
            "Min Option Bid ($)",
            min_value=0.0, max_value=10.0,
            value=0.20, step=0.10,
            format="%.2f",
            key="cc_min_premium",
            help="Minimum option bid price. Avoids illiquid penny options.",
        )

st.markdown("---")

# --- Gruppe 4: Sektor-Status ---
with st.container():
    st.markdown("##### Sektor-Status")

    if sector_quadrants:
        sec_col1, sec_col2, sec_col3 = st.columns([2, 2, 1])
        with sec_col1:
            sector_filter = st.multiselect(
                "Sektor-Filter",
                options=all_sectors_with_quadrant,
                default=[],
                key="cc_sector_filter",
                help="Nur Aktien aus diesen Sektoren zeigen. Leer = alle.",
                placeholder="Alle Sektoren",
            )
        with sec_col2:
            quadrant_filter = st.multiselect(
                "Quadrant-Filter (Sektor-Status)",
                options=available_quadrants,
                default=[],
                key="cc_quadrant_filter",
                placeholder="Alle Quadranten",
                help="🟢 Leading = Stärke. 🟠 Weakening / 🔴 Lagging = schwächer (konservativere Covered Calls).",
                format_func=lambda q: f"{_QUADRANT_EMOJI.get(q, '⚪')} {q}",
            )
        with sec_col3:
            exclude_leading = st.toggle(
                "Ohne Leading",
                value=False,
                key="cc_exclude_leading",
                help="Blendet Aktien aus Leading-Sektoren aus — für konservativere, defensivere Covered Calls.",
            )

        # Aktuellen Sektor-Status als Übersicht anzeigen
        if sector_quadrants:
            badges = " &nbsp; ".join(
                _sector_badge_html(s, q) for s, q in sorted(sector_quadrants.items())
            )
            st.markdown(f"<div style='margin:4px 0 2px 0;line-height:2.2;'>{badges}</div>",
                        unsafe_allow_html=True)
    else:
        sector_filter = []
        quadrant_filter = []
        exclude_leading = False
        st.caption("Sektor-Rotation-Daten nicht verfügbar.")

scan_btn = st.button("🔍 Scan for Covered Calls", type="primary")

# ── Load data ─────────────────────────────────────────────────────────────────
if scan_btn:
    with st.spinner("Scanning for ITM Covered Call opportunities..."):
        try:
            sql_path = PATH_DATABASE_QUERY_FOLDER / "covered_call_scanner.sql"
            raw_df = select_into_dataframe(
                sql_file_path=sql_path,
                params={
                    "delta_target":   delta_target,
                    "dte_min":        dte_min,
                    "dte_max":        dte_max,
                    "min_oi":         min_oi,
                    "min_market_cap": int(min_market_cap_b * 1e9),
                },
            )

            if raw_df.empty:
                st.warning("No results found. Try relaxing the filters.")
                st.session_state["cc_df"] = None
            else:
                # Numeric coercion
                num_cols = ["stock_price", "strike_price", "premium", "dte", "delta",
                            "iv_pct", "net_debit", "assigned_return_pct",
                            "annualized_return_pct", "downside_protection_pct",
                            "iv_rank", "iv_percentile", "hv_30d_pct",
                            "market_cap_b", "trailing_pe"]
                for col in num_cols:
                    if col in raw_df.columns:
                        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")

                # Sektor-Quadrant anreichern
                if sector_quadrants and "company_sector" in raw_df.columns:
                    raw_df["sektor_quadrant"] = raw_df["company_sector"].map(sector_quadrants).fillna("Unbekannt")
                else:
                    raw_df["sektor_quadrant"] = "Unbekannt"

                # Apply post-filters
                df = raw_df[
                    (raw_df["annualized_return_pct"] >= min_annualized) &
                    (raw_df["annualized_return_pct"] <= max_annualized) &
                    (raw_df["downside_protection_pct"] >= min_downside) &
                    (raw_df["delta"] <= delta_target_max)
                ].copy()

                # IV Rank filter
                if min_iv_rank > 0:
                    df = df[df["iv_rank"].isna() | (df["iv_rank"] >= min_iv_rank)]

                # Min option bid/premium filter
                if min_premium > 0:
                    df = df[df["premium"] >= min_premium]

                # Stock price range filter
                if price_min > 0:
                    df = df[df["stock_price"] >= price_min]
                if price_max > 0:
                    df = df[df["stock_price"] <= price_max]

                # Sektor-Filter
                if sector_filter:
                    df = df[df["company_sector"].isin(sector_filter)]
                if quadrant_filter:
                    df = df[df["sektor_quadrant"].isin(quadrant_filter)]
                if exclude_leading:
                    df = df[df["sektor_quadrant"] != "Leading"]

                if df.empty:
                    st.warning("All results filtered out. Try lowering Min Annualized Return or Min Downside Protection.")
                    st.session_state["cc_df"] = None
                else:
                    st.session_state["cc_df"] = df
                    st.session_state["cc_selected_idx"] = None
                    st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")
            logger.error(e, exc_info=True)

# ── Results table ─────────────────────────────────────────────────────────────
if st.session_state["cc_df"] is not None:
    df = st.session_state["cc_df"].copy()

    st.divider()
    st.subheader(f"Results — {len(df)} opportunities found")
    st.caption("Sorted by Annualized Return. Click a row for detailed analysis.")

    def _earnings_flag(row):
        dte = row.get("dte")
        days_earn = row.get("days_to_earnings")
        if pd.isna(days_earn):
            return "—"
        if days_earn <= (dte or 99):
            return "⚠️ vor Verfall"
        return f"✅ Safe ({int(days_earn)}d)"

    def _quadrant_cell(row):
        q = row.get("sektor_quadrant", "Unbekannt")
        emoji = _QUADRANT_EMOJI.get(q, "⚪")
        return f"{emoji} {q}"

    display_df = pd.DataFrame({
        "Symbol":        df["symbol"],
        "Sektor":        df["company_sector"].fillna("—"),
        "Quadrant":      df.apply(_quadrant_cell, axis=1),
        "Stock ($)":     df["stock_price"].apply(lambda v: f"{v:.2f}"),
        "Strike ($)":    df["strike_price"].apply(lambda v: f"{v:.2f}"),
        "Premium ($)":   df["premium"].apply(lambda v: f"{v:.2f}"),
        "DTE":           df["dte"].astype("Int64"),
        "Expiry":        df["expiration_date"].astype(str),
        "Net Debit ($)": df["net_debit"].apply(lambda v: f"{v:.2f}"),
        "Assigned %":    df["assigned_return_pct"].apply(lambda v: f"{v:.2f}%"),
        "Annual. %":     df["annualized_return_pct"].apply(lambda v: f"{v:.1f}%"),
        "Protection %":  df["downside_protection_pct"].apply(lambda v: f"{v:.1f}%"),
        "Delta":         df["delta"].apply(lambda v: f"{v:.3f}"),
        "IV Rank":       df["iv_rank"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—"),
        "Earnings":      df.apply(_earnings_flag, axis=1),
    })

    # Post-scan Tabellenfilter (wie Roll & Screen)
    tf1, tf2, tf3 = st.columns([2, 2, 1])
    tbl_sectors = tf1.multiselect(
        "Sektor (Tabelle)",
        options=sorted(df["company_sector"].dropna().unique()),
        default=[],
        key="cc_tbl_sector",
        placeholder="Alle",
    )
    tbl_quadrants = tf2.multiselect(
        "Quadrant (Tabelle)",
        options=sorted(df["sektor_quadrant"].unique()),
        default=[],
        key="cc_tbl_quadrant",
        placeholder="Alle",
        format_func=lambda q: f"{_QUADRANT_EMOJI.get(q, '⚪')} {q}",
    )

    view = display_df.copy()
    if tbl_sectors:
        view = view[view["Sektor"].isin(tbl_sectors)]
    if tbl_quadrants:
        view = view[view["Quadrant"].str.contains("|".join(tbl_quadrants), na=False)]

    # Colour-code by annualized return
    def _highlight(row):
        try:
            val = float(row["Annual. %"].replace("%", ""))
        except Exception:
            return [""] * len(row)
        if val >= 30:
            return ["background-color: rgba(20, 83, 45, 0.25)"] * len(row)
        if val >= 15:
            return ["background-color: rgba(120, 80, 0, 0.18)"] * len(row)
        return [""] * len(row)

    styled = view.style.apply(_highlight, axis=1).hide(axis="index")

    event = st.dataframe(
        styled,
        use_container_width=True,
        height=min(700, 40 + 35 * len(view)),
        selection_mode="single-row",
        on_select="rerun",
        key="cc_table",
    )

    st.caption("Green = Annualized Return ≥ 30% | Amber = ≥ 15%")

    # ── Inline documentation on row click ────────────────────────────────────
    selected = event.selection.rows if hasattr(event, "selection") else []
    if selected:
        idx = selected[0]
        # view.index carries the original df positional index after filtering
        r = df.loc[view.index[idx]]

        symbol       = r["symbol"]
        stock        = float(r["stock_price"])
        strike       = float(r["strike_price"])
        premium      = float(r["premium"])
        dte          = int(r["dte"])
        net_debit    = float(r["net_debit"])
        assigned_ret = float(r["assigned_return_pct"])
        annualized   = float(r["annualized_return_pct"])
        protection   = float(r["downside_protection_pct"])
        delta_val    = float(r["delta"])
        iv_rank      = float(r["iv_rank"]) if pd.notna(r.get("iv_rank")) else None
        hv           = float(r["hv_30d_pct"]) if pd.notna(r.get("hv_30d_pct")) else None
        expiry       = str(r["expiration_date"])
        earnings     = str(r.get("earnings_date", "—"))
        days_earn    = r.get("days_to_earnings")
        sector_en    = str(r.get("company_sector", ""))
        quadrant     = str(r.get("sektor_quadrant", "Unbekannt"))

        breakeven    = round(net_debit, 2)
        max_profit   = round((strike - net_debit) * 100, 2)
        close_50pct  = round(premium * 0.50, 2)

        # IV commentary
        if iv_rank is not None:
            if iv_rank >= 60:
                iv_comment = f"IV Rank {iv_rank:.0f}% — options are expensive, good time to sell."
            elif iv_rank >= 40:
                iv_comment = f"IV Rank {iv_rank:.0f}% — options are fairly priced."
            else:
                iv_comment = f"IV Rank {iv_rank:.0f}% — options are cheap, premium may be thin."
        else:
            iv_comment = "IV Rank not available."

        # IV vs HV
        if hv is not None and iv_rank is not None:
            iv_approx = r.get("iv_pct")
            if pd.notna(iv_approx):
                iv_hv_text = (
                    f"Current IV ({float(iv_approx):.1f}%) vs HV 30d ({hv:.1f}%) — "
                    + ("IV is elevated, options are overpriced relative to realized moves. Good for selling."
                       if float(iv_approx) > hv else
                       "IV is in line with realized volatility.")
                )
            else:
                iv_hv_text = ""
        else:
            iv_hv_text = ""

        # Earnings warning
        if pd.notna(days_earn) and days_earn <= dte:
            earn_warning = f"> **Earnings on {earnings} ({int(days_earn)} days) fall BEFORE expiry ({dte} DTE). IV crush risk — consider a shorter expiry.**"
        else:
            earn_warning = f"Earnings on {earnings} are after expiry — no IV crush risk for this position."

        st.divider()
        st.subheader(f"Trade Analysis — {symbol}")

        # ── Banner ────────────────────────────────────────────────────────────
        if annualized >= 30:
            _bg, _brd, _tag = "#166534", "#22c55e", "🟢 STARK"
        elif annualized >= 15:
            _bg, _brd, _tag = "#854d0e", "#f59e0b", "🟡 SOLIDE"
        else:
            _bg, _brd, _tag = "#374151", "#9ca3af", "⚪ MODERAT"

        sector_badge = _sector_badge_html(sector_en, quadrant) if sector_en else ""

        st.markdown(
            f"<div style='background:{_bg};border:2px solid {_brd};border-radius:10px;"
            f"padding:14px 18px;margin:6px 0 12px 0;'>"
            f"<span style='color:#fff;font-size:26px;font-weight:800;'>{_tag} · "
            f"{annualized:.1f}% p.a.</span>"
            f"<span style='color:#e5e7eb;font-size:16px;font-weight:600;'> &nbsp;"
            f"({assigned_ret:.2f}% in {dte} Tagen)</span>"
            f"<br><span style='color:#e5e7eb;font-size:13px;'>"
            f"{symbol} @ ${stock:.2f} &nbsp;·&nbsp; Strike ${strike:.2f} &nbsp;·&nbsp; "
            f"Net Debit ${net_debit:.2f} &nbsp;·&nbsp; Breakeven ${breakeven:.2f} &nbsp;·&nbsp; "
            f"Downside-Puffer {protection:.1f}% &nbsp;·&nbsp; Verfall {expiry}"
            f"</span>"
            f"<br><span style='margin-top:6px;display:inline-block;'>{sector_badge}</span>"
            f"</div>", unsafe_allow_html=True)

        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Net Debit", f"${net_debit:.2f}", help="Dein realer Einstand pro Aktie (Kurs − Prämie)")
        m2.metric("Assigned Return", f"{assigned_ret:.2f}%", help="Gewinn, wenn die Aktie am Verfall ausgeübt/abgerufen wird")
        m3.metric("Annualized Return", f"{annualized:.1f}%", help="Auf ein Jahr hochgerechnet")
        m4.metric("Downside Protection", f"{protection:.1f}%", help="Wie weit die Aktie fallen darf, bis du ins Minus kommst")

        # ── Graphen nebeneinander ─────────────────────────────────────────────
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.markdown("**📊 Payoff bei Verfall**")
            _render_payoff_chart(stock, strike, premium, net_debit, dte)
        with chart_col2:
            st.markdown("**📈 IV-Rank Historie (1 Jahr)**")
            _render_iv_chart(symbol)

        # ── Erklär-Blöcke ─────────────────────────────────────────────────────
        with st.expander("🧮 Wie berechnen sich die Kennzahlen?", expanded=True):
            st.markdown(f"""
| Kennzahl | Rechnung | Ergebnis |
|---|---|---|
| **Net Debit** | ${stock:.2f} Kurs − ${premium:.2f} Prämie | **${net_debit:.2f}** |
| **Assigned Return** | (${strike:.2f} Strike − ${net_debit:.2f} Einstand) / ${net_debit:.2f} × 100 | **{assigned_ret:.2f}%** |
| **Annualized Return** | {assigned_ret:.2f}% / {dte} Tage × 365 | **{annualized:.1f}%** |
| **Downside Protection** | ${premium:.2f} Prämie / ${stock:.2f} Kurs × 100 | **{protection:.1f}%** |
""")

        with st.expander("📊 Gewinn & Verlust am Verfall", expanded=True):
            st.markdown(f"""
- 🟢 **Bestfall — Aktie über ${strike:.2f}:** Aktien werden abgerufen → **+${max_profit:.2f} pro Kontrakt** (+{assigned_ret:.2f}%). Mehr geht nicht (Gewinn gedeckelt).
- ⚪ **Breakeven bei ${breakeven:.2f}:** genau dein Einstand → $0.
- 🔴 **Unter ${breakeven:.2f}:** Verlust = (${breakeven:.2f} − Kurs) × 100 pro Kontrakt. Die Prämie hat dich bis hier abgefedert ({protection:.1f}% Puffer).
""")

        with st.expander("🚪 Früher Ausstieg — 50%-Regel", expanded=False):
            st.markdown(f"""
Gängige Praxis: schließen, wenn die Prämie auf 50% gefallen ist.

- Verkauft für: **${premium:.2f}**
- Zurückkaufen bei: **${close_50pct:.2f}** (buy-to-close)
- Gewinn: **${round(premium - close_50pct, 2):.2f} pro Aktie** in ≤ {dte} Tagen → dann Kapital in die nächste Chance.
""")

        with st.expander("📈 Volatilität, Earnings & Delta", expanded=False):
            _delta_txt = ("Sehr tief im Geld — hohe Zuteilungs-Wahrscheinlichkeit, faktisch ein fixer Income-Trade."
                          if delta_val >= 0.8 else
                          "Moderat im Geld — ausgewogenes Verhältnis aus Prämie und Zuteilungs-Wahrscheinlichkeit.")
            st.markdown(f"""
- **Volatilität:** {iv_comment} {iv_hv_text}
- **Earnings:** {earn_warning}
- **Delta {delta_val:.3f}:** die Option bewegt sich ~${delta_val:.2f} je $1 Aktienbewegung; Zuteilungs-Wahrscheinlichkeit am Verfall ≈ **{delta_val*100:.0f}%**. {_delta_txt}
""")

    else:
        st.caption("Click a row to see detailed trade analysis and P&L breakdown.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "ITM Covered Call Scanner — PowerOptions MorningUpdate methodology | "
    "Data: OptionDataMerged + StockData"
)
