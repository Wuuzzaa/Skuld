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

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

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

# ── Filter controls ───────────────────────────────────────────────────────────
st.subheader("Scanner Filters")

col1, col2, col3 = st.columns(3)
with col1:
    dte_min, dte_max = st.slider(
        "DTE Range (days to expiration)",
        min_value=7, max_value=90,
        value=(7, 90), step=1,
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

col4, col5, col6 = st.columns(3)
with col4:
    min_annualized = st.number_input(
        "Min Annualized Return %",
        min_value=0, max_value=200,
        value=5, step=5,
        key="cc_min_ann",
        help="Untergrenze der annualisierten Rendite.",
    )
with col5:
    max_annualized = st.number_input(
        "Max Annualized Return %",
        min_value=10, max_value=1000,
        value=200, step=10,
        key="cc_max_ann",
        help="Cap utopian values. Anything above ~200% is usually a data artefact or illiquid option.",
    )
with col6:
    min_market_cap_b = st.number_input(
        "Min Market Cap ($B)",
        min_value=0.0, max_value=50.0,
        value=1.0, step=0.5,
        format="%.1f",
        key="cc_min_cap",
    )

col7, col8, col9 = st.columns(3)
with col7:
    min_oi = st.number_input(
        "Min Open Interest",
        min_value=0, max_value=1000,
        value=50, step=25,
        key="cc_min_oi",
    )
with col8:
    min_downside = st.slider(
        "Min Downside Protection %",
        min_value=0, max_value=40,
        value=0, step=1,
        key="cc_min_downside",
        help="Filter out positions with insufficient downside buffer.",
    )
with col9:
    price_min = st.number_input(
        "Min Stock Price ($)",
        min_value=0.0, max_value=10000.0,
        value=0.0, step=5.0, format="%.0f",
        key="cc_price_min",
        help="Nur Aktien mit Kurs ≥ diesem Wert. 0 = keine Untergrenze.",
    )

col10, col11, col12 = st.columns(3)
with col10:
    min_iv_rank = st.number_input(
        "Min IV Rank",
        min_value=0, max_value=100,
        value=0, step=5,
        key="cc_min_iv_rank",
        help="0 = deaktiviert. IV Rank ≥ 50 stellt sicher dass Optionen teuer genug zum Verkaufen sind.",
    )
with col11:
    min_premium = st.number_input(
        "Min Option Bid ($)",
        min_value=0.0, max_value=10.0,
        value=0.20, step=0.10,
        format="%.2f",
        key="cc_min_premium",
        help="Minimum option bid price. Avoids illiquid penny options.",
    )
with col12:
    price_max = st.number_input(
        "Max Stock Price ($)",
        min_value=0.0, max_value=10000.0,
        value=0.0, step=5.0, format="%.0f",
        key="cc_price_max",
        help="Nur Aktien mit Kurs ≤ diesem Wert. 0 = keine Obergrenze.",
    )

with st.expander("🎯 Quality Filters (Vorauswahl für realistische Trades)", expanded=True):
    st.caption("Jeden Filter einzeln ein-/ausschalten. Aktiv = Haken gesetzt.")
    qcol1, qcol2, qcol3 = st.columns(3)

    with qcol1:
        qf_max_ann = st.checkbox("Max Annualized ≤ 50%", value=True, key="qf_max_ann",
            help="Returns über 50% p.a. sind meist Datenmüll oder illiquide Strikes.")
        qf_min_ann = st.checkbox("Min Annualized ≥ 15%", value=True, key="qf_min_ann",
            help="Unter 15% p.a. lohnt sich das Kapital-Risiko kaum.")

    with qcol2:
        qf_protection = st.checkbox("Min Downside Protection ≥ 10%", value=True, key="qf_protection",
            help="Mindestens 10% Puffer bevor du Verlust machst.")
        qf_mcap = st.checkbox("Min Market Cap ≥ $5B", value=True, key="qf_mcap",
            help="Kleine Caps haben oft illiquide Options und hohe Bid/Ask-Spreads.")

    with qcol3:
        qf_earnings = st.checkbox("Earnings vor Verfall ausschließen", value=True, key="qf_earnings",
            help="Aktien mit Earnings innerhalb der Halteperiode rausfiltern — IV-Crush-Risiko.")
        qf_iv_rank = st.checkbox("Min IV Rank ≥ 30%", value=False, key="qf_iv_rank",
            help="Nur Optionen verkaufen wenn IV erhöht ist. Deaktiviert = auch niedrige IV.")

# Qualitätsfilter-Werte ableiten (überschreiben die manuellen Filter wenn aktiver Haken)
_max_annualized  = 50   if qf_max_ann   else max_annualized
_min_annualized  = 15   if qf_min_ann   else min_annualized
_min_downside    = 10   if qf_protection else min_downside
_min_market_cap  = 5.0  if qf_mcap      else min_market_cap_b
_exclude_earnings = qf_earnings
_min_iv_rank_eff = 30   if qf_iv_rank   else min_iv_rank

scan_btn = st.button("Scan for Covered Calls", type="primary")

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
                    "min_iv_rank":    min_iv_rank,
                },
            )

            if raw_df.empty:
                st.warning("No results found. Try relaxing the filters.")
                st.session_state["cc_df"] = None
            else:
                # Numeric coercion
                num_cols = ["stock_price", "strike_price", "last_price", "dte", "delta",
                            "iv_pct", "net_debit", "break_even", "pct_be",
                            "moneyness_pct", "assigned_return_pct",
                            "annualized_return_pct", "downside_protection_pct",
                            "potential_return_pct", "profit_prob_pct",
                            "max_profit_contract", "iv_hv_ratio",
                            "iv_rank", "iv_percentile", "hv_30d_pct",
                            "market_cap_b", "trailing_pe"]
                for col in num_cols:
                    if col in raw_df.columns:
                        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")

                # Apply post-filters (Quality Filters überschreiben manuelle wenn aktiv)
                df = raw_df[
                    (raw_df["annualized_return_pct"] >= _min_annualized) &
                    (raw_df["annualized_return_pct"] <= _max_annualized) &
                    (raw_df["downside_protection_pct"] >= _min_downside) &
                    (raw_df["delta"] <= delta_target_max)
                ].copy()

                # IV Rank filter
                if _min_iv_rank_eff > 0:
                    df = df[df["iv_rank"].isna() | (df["iv_rank"] >= _min_iv_rank_eff)]

                # Market Cap filter
                if _min_market_cap > 0:
                    df = df[df["market_cap_b"] >= _min_market_cap]

                # Min option bid/premium filter
                if min_premium > 0:
                    df = df[df["last_price"] >= min_premium]

                # Stock price range filter (0 = keine Grenze)
                if price_min > 0:
                    df = df[df["stock_price"] >= price_min]
                if price_max > 0:
                    df = df[df["stock_price"] <= price_max]

                # Earnings-Filter
                if _exclude_earnings:
                    df = df[
                        df["days_to_earnings"].isna() |
                        (df["days_to_earnings"] > df["dte"])
                    ]

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
            return "Earnings before expiry"
        return f"Safe ({int(days_earn)}d)"

    display_df = pd.DataFrame({
        "Symbol":           df["symbol"],
        "Sector":           df["company_sector"].fillna("—"),
        "Stock ($)":        df["stock_price"].apply(lambda v: f"{v:.2f}"),
        "Exp Date":         df["expiration_date"].astype(str),
        "DTE":              df["dte"].astype("Int64"),
        "Strike ($)":       df["strike_price"].apply(lambda v: f"{v:.2f}"),
        "Moneyness":        df["moneyness_pct"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—"),
        "Last ($)":         df["last_price"].apply(lambda v: f"{v:.2f}"),
        "BE (Last)":        df["break_even"].apply(lambda v: f"{v:.2f}"),
        "%BE":              df["pct_be"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—"),
        "Volume":           df["volume"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
        "Open Int":         df["open_interest"].apply(lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
        "IV Rank":          df["iv_rank"].apply(lambda v: f"{v:.0f}%" if pd.notna(v) else "—"),
        "IV/HV":            df["iv_hv_ratio"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Delta":            df["delta"].apply(lambda v: f"{v:.3f}"),
        "Return %":         df["assigned_return_pct"].apply(lambda v: f"{v:.2f}%"),
        "Ann Rtn %":        df["annualized_return_pct"].apply(lambda v: f"{v:.1f}%"),
        "Ptnl Rtn %":       df["potential_return_pct"].apply(lambda v: f"{v:.2f}%" if pd.notna(v) else "—"),
        "Profit Prob %":    df["profit_prob_pct"].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—"),
        "Max Profit ($)":   df["max_profit_contract"].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Protection %":     df["downside_protection_pct"].apply(lambda v: f"{v:.1f}%"),
        "Earnings":         df.apply(_earnings_flag, axis=1),
    })

    # Colour-code by annualized return
    def _highlight(row):
        try:
            val = float(row["Ann Rtn %"].replace("%", ""))
        except Exception:
            return [""] * len(row)
        if val >= 30:
            return ["background-color: rgba(20, 83, 45, 0.25)"] * len(row)
        if val >= 15:
            return ["background-color: rgba(120, 80, 0, 0.18)"] * len(row)
        return [""] * len(row)

    styled = display_df.style.apply(_highlight, axis=1).hide(axis="index")

    event = st.dataframe(
        styled,
        use_container_width=True,
        height=min(700, 40 + 35 * len(display_df)),
        selection_mode="single-row",
        on_select="rerun",
        key="cc_table",
    )

    st.caption("Green = Annualized Return ≥ 30% | Amber = ≥ 15%")

    # ── Inline documentation on row click ────────────────────────────────────
    selected = event.selection.rows if hasattr(event, "selection") else []
    if selected:
        idx = selected[0]
        r = df.iloc[idx]

        symbol           = r["symbol"]
        stock            = float(r["stock_price"])
        strike           = float(r["strike_price"])
        last_price       = float(r["last_price"])
        dte              = int(r["dte"])
        net_debit        = float(r["net_debit"])
        assigned_ret     = float(r["assigned_return_pct"])
        annualized       = float(r["annualized_return_pct"])
        protection       = float(r["downside_protection_pct"])
        delta_val        = float(r["delta"])
        iv_rank          = float(r["iv_rank"]) if pd.notna(r.get("iv_rank")) else None
        hv               = float(r["hv_30d_pct"]) if pd.notna(r.get("hv_30d_pct")) else None
        expiry           = str(r["expiration_date"])
        earnings         = str(r.get("earnings_date", "—"))
        days_earn        = r.get("days_to_earnings")
        moneyness        = float(r["moneyness_pct"]) if pd.notna(r.get("moneyness_pct")) else None
        pct_be           = float(r["pct_be"]) if pd.notna(r.get("pct_be")) else None
        potential_rtn    = float(r["potential_return_pct"]) if pd.notna(r.get("potential_return_pct")) else None
        profit_prob      = float(r["profit_prob_pct"]) if pd.notna(r.get("profit_prob_pct")) else None
        max_profit_c     = float(r["max_profit_contract"]) if pd.notna(r.get("max_profit_contract")) else None
        iv_hv_ratio      = float(r["iv_hv_ratio"]) if pd.notna(r.get("iv_hv_ratio")) else None

        breakeven        = round(net_debit, 2)
        max_profit       = round((strike - net_debit) * 100, 2)
        close_50pct      = round(last_price * 0.50, 2)

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

        import plotly.graph_objects as go
        import numpy as np
        from src.ui_strategy_display import display_external_links

        st.divider()
        st.subheader(f"Trade Analysis — {symbol}")

        # ── Banner ────────────────────────────────────────────────────────────
        if annualized >= 30:
            _bg, _brd, _tag = "#166534", "#22c55e", "🟢 STARK"
        elif annualized >= 15:
            _bg, _brd, _tag = "#854d0e", "#f59e0b", "🟡 SOLIDE"
        else:
            _bg, _brd, _tag = "#374151", "#9ca3af", "⚪ MODERAT"
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
            f"Downside-Puffer {protection:.1f}% &nbsp;·&nbsp; Verfall {expiry}</span>"
            f"</div>", unsafe_allow_html=True)

        # ── Firmeninfo + Sektor ───────────────────────────────────────────────
        company_name = str(r.get("company_name", "")) or symbol
        company_sector = str(r.get("company_sector", "")) or "—"
        market_cap_b = float(r["market_cap_b"]) if pd.notna(r.get("market_cap_b")) else None
        trailing_pe  = float(r["trailing_pe"])  if pd.notna(r.get("trailing_pe"))  else None
        avg_volume   = float(r["avg_volume"])    if pd.notna(r.get("avg_volume"))   else None

        fi1, fi2, fi3, fi4 = st.columns(4)
        fi1.markdown(f"**{company_name}**  \n{company_sector}")
        fi2.metric("Market Cap", f"${market_cap_b:.1f}B" if market_cap_b else "—")
        fi3.metric("Trailing P/E", f"{trailing_pe:.1f}" if trailing_pe else "—")
        fi4.metric("Avg Volume", f"{int(avg_volume/1e6):.1f}M" if avg_volume and avg_volume >= 1e6 else (f"{int(avg_volume/1e3):.0f}K" if avg_volume else "—"))

        st.divider()

        # ── Kennzahlen-Grid ───────────────────────────────────────────────────
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Last Price",          f"${last_price:.2f}",   help="Letzter Handelspreis der Option")
        m2.metric("Net Debit",           f"${net_debit:.2f}",    help="Kurs − Prämie = dein echter Einstand")
        m3.metric("Break Even",          f"${breakeven:.2f}",    help="Aktie muss darüber bleiben für kein Verlust")
        m4.metric("Assigned Return",     f"{assigned_ret:.2f}%", help="Gewinn wenn Aktien abgerufen werden")
        m5.metric("Annualized Return",   f"{annualized:.1f}%",   help="Normiert auf 365 Tage")
        m6.metric("Downside Protection", f"{protection:.1f}%",   help="Puffer bevor du Verlust machst")

        m7, m8, m9, m10, m11, m12 = st.columns(6)
        m7.metric("Moneyness",           f"{moneyness:.2f}%"     if moneyness    is not None else "—", help="(Strike−Kurs)/Kurs×100; negativ = ITM")
        m8.metric("Potential Return",    f"{potential_rtn:.2f}%" if potential_rtn is not None else "—", help="Upside vom aktuellen Kurs bis Strike")
        m9.metric("Profit Probability",  f"{profit_prob:.1f}%"   if profit_prob  is not None else "—", help="≈ (1−Delta)×100: Call verfällt OTM")
        m10.metric("Max Profit/Contract",f"${max_profit_c:.2f}"  if max_profit_c is not None else "—", help="(Strike−NetDebit)×100")
        m11.metric("IV Rank",            f"{iv_rank:.0f}%"       if iv_rank      is not None else "—", help="Wie teuer die Optionen historisch gesehen sind")
        m12.metric("IV/HV Ratio",        f"{iv_hv_ratio:.2f}"    if iv_hv_ratio  is not None else "—", help="IV > 1.0 = Optionen teurer als realisierte Vola")

        # ── Payoff-Chart + IV-Gauge nebeneinander ─────────────────────────────
        chart_col, gauge_col = st.columns([3, 1])

        with chart_col:
            price_range = np.linspace(stock * 0.70, stock * 1.15, 300)
            pnl = np.where(
                price_range >= strike,
                (strike - net_debit) * 100,
                (price_range - net_debit) * 100,
            )
            fig_payoff = go.Figure()
            fig_payoff.add_shape(type="rect",
                x0=stock * 0.70, x1=breakeven, y0=min(pnl) * 1.1, y1=0,
                fillcolor="rgba(239,68,68,0.08)", line_width=0)
            fig_payoff.add_shape(type="rect",
                x0=breakeven, x1=stock * 1.15, y0=0, y1=max(pnl) * 1.1,
                fillcolor="rgba(34,197,94,0.08)", line_width=0)
            fig_payoff.add_trace(go.Scatter(
                x=price_range, y=pnl,
                mode="lines", line=dict(color="#3b82f6", width=3),
                name="P&L bei Verfall",
                hovertemplate="Kurs: $%{x:.2f}<br>P&L: $%{y:.2f}<extra></extra>",
            ))
            for xval, label, color, dash in [
                (stock,     f"Kurs ${stock:.2f}",         "#f59e0b", "dot"),
                (strike,    f"Strike ${strike:.2f}",      "#a78bfa", "dash"),
                (breakeven, f"BE ${breakeven:.2f}",       "#ef4444", "dashdot"),
            ]:
                fig_payoff.add_vline(x=xval, line_color=color, line_dash=dash, line_width=1.5,
                    annotation_text=label, annotation_position="top",
                    annotation_font_color=color, annotation_font_size=11)
            fig_payoff.add_hline(y=0, line_color="#6b7280", line_width=1)
            fig_payoff.update_layout(
                title=f"P&L bei Verfall — {symbol} ITM Covered Call",
                xaxis_title="Aktienkurs bei Verfall ($)",
                yaxis_title="P&L pro Kontrakt ($)",
                height=340, margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", y=-0.15),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#e5e7eb"),
                xaxis=dict(gridcolor="#374151"), yaxis=dict(gridcolor="#374151"),
            )
            st.plotly_chart(fig_payoff, use_container_width=True)

        with gauge_col:
            iv_gauge_val = iv_rank if iv_rank is not None else 0
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=iv_gauge_val,
                title={"text": "IV Rank %", "font": {"color": "#e5e7eb", "size": 13}},
                number={"suffix": "%", "font": {"color": "#e5e7eb", "size": 22}},
                gauge={
                    "axis": {"range": [0, 100], "tickcolor": "#6b7280", "tickfont": {"color": "#9ca3af", "size": 10}},
                    "bar": {"color": "#3b82f6", "thickness": 0.3},
                    "bgcolor": "#1f2937",
                    "bordercolor": "#374151",
                    "steps": [
                        {"range": [0, 30],  "color": "#374151"},
                        {"range": [30, 50], "color": "#78350f"},
                        {"range": [50, 100],"color": "#14532d"},
                    ],
                    "threshold": {"line": {"color": "#ef4444", "width": 3}, "thickness": 0.75, "value": 50},
                },
            ))
            fig_gauge.update_layout(
                height=220, margin=dict(l=10, r=10, t=30, b=10),
                paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#e5e7eb"),
            )
            st.plotly_chart(fig_gauge, use_container_width=True)
            if iv_rank is not None:
                if iv_rank >= 50:
                    st.success(f"IV erhöht ({iv_rank:.0f}%) — guter Zeitpunkt zum Verkaufen")
                elif iv_rank >= 30:
                    st.warning(f"IV moderat ({iv_rank:.0f}%) — akzeptabel")
                else:
                    st.error(f"IV niedrig ({iv_rank:.0f}%) — Prämie ist dünn")

        # ── Expander: Kennzahlen-Tabelle ──────────────────────────────────────
        with st.expander("🧮 Wie berechnen sich die Kennzahlen?", expanded=False):
            iv_pct_val = float(r["iv_pct"]) if pd.notna(r.get("iv_pct")) else None
            st.markdown(f"""
| Kennzahl | Rechnung | Ergebnis |
|---|---|---|
| **Last Price** | Letzter Handelspreis der Option | **${last_price:.2f}** |
| **Net Debit** | ${stock:.2f} Kurs − ${last_price:.2f} Prämie | **${net_debit:.2f}** |
| **Break Even** | = Net Debit | **${breakeven:.2f}** ({f"{pct_be:.2f}%" if pct_be is not None else "—"} vom Kurs) |
| **Moneyness** | (${strike:.2f} − ${stock:.2f}) / ${stock:.2f} × 100 | **{f"{moneyness:.2f}%" if moneyness is not None else "—"}** |
| **Assigned Return** | (${strike:.2f} − ${net_debit:.2f}) / ${net_debit:.2f} × 100 | **{assigned_ret:.2f}%** |
| **Annualized Return** | {assigned_ret:.2f}% / {dte} Tage × 365 | **{annualized:.1f}%** |
| **Downside Protection** | ${last_price:.2f} / ${stock:.2f} × 100 | **{protection:.1f}%** |
| **Potential Return** | (${strike:.2f} − ${stock:.2f}) / ${stock:.2f} × 100 | **{f"{potential_rtn:.2f}%" if potential_rtn is not None else "—"}** |
| **Profit Probability** | (1 − {delta_val:.3f}) × 100 | **{f"{profit_prob:.1f}%" if profit_prob is not None else "—"}** |
| **Max Profit / Contract** | (${strike:.2f} − ${net_debit:.2f}) × 100 | **{f"${max_profit_c:.2f}" if max_profit_c is not None else "—"}** |
| **IV/HV Ratio** | {f"{iv_pct_val:.1f}% IV" if iv_pct_val else "IV?"} / {f"{hv:.1f}% HV" if hv else "HV?"} | **{f"{iv_hv_ratio:.2f}" if iv_hv_ratio is not None else "—"}** |
""")

        # ── Expander: P&L Szenarien ───────────────────────────────────────────
        with st.expander("📊 Gewinn & Verlust — Szenarien", expanded=True):
            sc1, sc2, sc3 = st.columns(3)
            sc1.success(f"**Bestfall**  \nAktie ≥ ${strike:.2f}  \n**+${max_profit:.2f}** pro Kontrakt  \n(+{assigned_ret:.2f}% in {dte}d)")
            sc2.info(   f"**Breakeven**  \nAktie = ${breakeven:.2f}  \n**$0** — kein Gewinn, kein Verlust")
            sc3.error(  f"**Schlimmfall**  \nAktie → $0  \nVerlust: **-${round(net_debit*100,2):.2f}**  \n(Puffer: {protection:.1f}% durch Prämie)")
            st.markdown(f"""
**Wie es funktioniert:**
- Aktie **über ${strike:.2f}** bei Verfall → Aktien werden abgerufen, du behältst die volle Prämie. Gewinn gedeckelt auf **${max_profit:.2f}**.
- Aktie **zwischen ${breakeven:.2f} und ${strike:.2f}** → Aktien nicht abgerufen, du behältst die Prämie aber weniger Gewinn durch Kursverlust.
- Aktie **unter ${breakeven:.2f}** → Verlust. Die Prämie hat dich um **{protection:.1f}%** abgefedert.
""")

        # ── Expander: Früher Ausstieg ─────────────────────────────────────────
        with st.expander("🚪 Früher Ausstieg — 50%-Regel", expanded=False):
            st.markdown(f"""
Gängige Praxis: Position schließen wenn die Prämie auf **50%** gefallen ist (buy-to-close).

| | Wert |
|---|---|
| Verkauft für (sell-to-open) | **${last_price:.2f}** |
| Buy-to-close Ziel (50%) | **${close_50pct:.2f}** |
| Realisierter Gewinn | **${round(last_price - close_50pct, 2):.2f} pro Aktie** |
| Verbleibendes Risiko danach | $0 — Position geschlossen |

Kapital nach 50%-Ausstieg sofort in die nächste Chance reinvestieren → höhere annualisierte Rendite als bis Verfall halten.
""")

        # ── Expander: Volatilität & Earnings ─────────────────────────────────
        with st.expander("📈 Volatilität, Earnings & Delta", expanded=False):
            iv_pct_val = float(r["iv_pct"]) if pd.notna(r.get("iv_pct")) else None
            _iv_hv_text = ""
            if iv_pct_val and hv:
                _iv_hv_text = (
                    f"IV ({iv_pct_val:.1f}%) **über** HV 30d ({hv:.1f}%) — Optionen sind teurer als realisierte Bewegungen. Gut zum Verkaufen."
                    if iv_pct_val > hv else
                    f"IV ({iv_pct_val:.1f}%) **unter** HV 30d ({hv:.1f}%) — Optionen billig relativ zur realisierten Vola."
                )
            _delta_txt = (
                "Sehr tief im Geld — hohe Zuteilungs-Wahrscheinlichkeit, faktisch ein fixer Income-Trade."
                if delta_val >= 0.8 else
                "Moderat im Geld — ausgewogenes Verhältnis aus Prämie und Zuteilungs-Wahrscheinlichkeit."
            )
            earn_icon = "⚠️" if pd.notna(days_earn) and days_earn <= dte else "✅"
            st.markdown(f"""
**IV Rank:** {iv_comment}
{_iv_hv_text}

**{earn_icon} Earnings:** {earn_warning}

**Delta {delta_val:.3f}:** Die Option bewegt sich ~${delta_val:.2f} je $1 Aktienbewegung.
Zuteilungs-Wahrscheinlichkeit am Verfall ≈ **{delta_val*100:.0f}%**. {_delta_txt}
""")

        # ── Externe Links (Standard wie Spreads-Seite) ────────────────────────
        st.divider()
        display_external_links(symbol)

    else:
        st.caption("Click a row to see detailed trade analysis and P&L breakdown.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "ITM Covered Call Scanner — PowerOptions MorningUpdate methodology | "
    "Data: OptionDataMerged + StockData"
)
