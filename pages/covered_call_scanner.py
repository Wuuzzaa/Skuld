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

scan_btn = st.button("Scan for Covered Calls", type="primary")
exclude_earnings = st.checkbox(
    "Earnings vor Verfall ausschließen",
    value=False,
    key="cc_exclude_earnings",
    help="Aktien mit Earnings-Termin innerhalb der Halteperiode herausfiltern. "
         "Deaktiviert = Earnings-Kandidaten werden angezeigt (mit Warnung in der Tabelle).",
)

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

                # Apply post-filters
                df = raw_df[
                    (raw_df["annualized_return_pct"] >= min_annualized) &
                    (raw_df["annualized_return_pct"] <= max_annualized) &
                    (raw_df["downside_protection_pct"] >= min_downside) &
                    (raw_df["delta"] <= delta_target_max)
                ].copy()

                # IV Rank filter (skip rows where iv_rank is NaN)
                if min_iv_rank > 0:
                    df = df[df["iv_rank"].isna() | (df["iv_rank"] >= min_iv_rank)]

                # Min option bid/premium filter
                if min_premium > 0:
                    df = df[df["last_price"] >= min_premium]

                # Stock price range filter (0 = keine Grenze)
                if price_min > 0:
                    df = df[df["stock_price"] >= price_min]
                if price_max > 0:
                    df = df[df["stock_price"] <= price_max]

                # Earnings-Filter (optional)
                if exclude_earnings:
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

        st.divider()
        st.subheader(f"Trade Analysis — {symbol}")

        # ── Großes, präsentes Ergebnis-Banner (grün ≥30 / amber ≥15 / grau) ──
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

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Last Price",         f"${last_price:.2f}",    help="Last traded option price (no Bid/Ask available)")
        m2.metric("Net Debit",          f"${net_debit:.2f}",     help="Stock Price − Last Price = your real cost basis")
        m3.metric("Break Even",         f"${breakeven:.2f}",     help="Stock must stay above this for no loss")
        m4.metric("Assigned Return",    f"{assigned_ret:.2f}%",  help="Profit if called away at expiry")
        m5.metric("Annualized Return",  f"{annualized:.1f}%",    help="Normalized across expirations")
        m6.metric("Downside Protection",f"{protection:.1f}%",    help="How far stock can fall before losing money")

        m7, m8, m9, m10 = st.columns(4)
        m7.metric("Moneyness",          f"{moneyness:.2f}%" if moneyness is not None else "—",    help="(Strike − Stock) / Stock × 100; negative = ITM")
        m8.metric("Potential Return",   f"{potential_rtn:.2f}%" if potential_rtn is not None else "—", help="Upside from current price to strike")
        m9.metric("Profit Probability", f"{profit_prob:.1f}%" if profit_prob is not None else "—",    help="≈ (1 − Delta) × 100: probability call expires OTM")
        m10.metric("Max Profit / Contract", f"${max_profit_c:.2f}" if max_profit_c is not None else "—", help="(Strike − Net Debit) × 100")

        # ── Erklär-Blöcke: kompakt, mit Icons, in Expandern ──────────────────
        with st.expander("🧮 Wie berechnen sich die Kennzahlen?", expanded=True):
            st.markdown(f"""
| Kennzahl | Rechnung | Ergebnis |
|---|---|---|
| **Last Price** | Letzter Handelspreis der Option | **${last_price:.2f}** |
| **Net Debit** | ${stock:.2f} Kurs − ${last_price:.2f} Last | **${net_debit:.2f}** |
| **Break Even** | = Net Debit = ${net_debit:.2f} | **${breakeven:.2f}** ({f"{pct_be:.2f}%" if pct_be is not None else "—"} vom Kurs) |
| **Moneyness** | (${strike:.2f} Strike − ${stock:.2f} Kurs) / ${stock:.2f} × 100 | **{f"{moneyness:.2f}%" if moneyness is not None else "—"}** |
| **Assigned Return** | (${strike:.2f} − ${net_debit:.2f}) / ${net_debit:.2f} × 100 | **{assigned_ret:.2f}%** |
| **Annualized Return** | {assigned_ret:.2f}% / {dte} Tage × 365 | **{annualized:.1f}%** |
| **Downside Protection** | ${last_price:.2f} / ${stock:.2f} × 100 | **{protection:.1f}%** |
| **Potential Return** | (${strike:.2f} − ${stock:.2f}) / ${stock:.2f} × 100 | **{f"{potential_rtn:.2f}%" if potential_rtn is not None else "—"}** |
| **Profit Probability** | (1 − {delta_val:.3f}) × 100 | **{f"{profit_prob:.1f}%" if profit_prob is not None else "—"}** |
| **Max Profit / Contract** | (${strike:.2f} − ${net_debit:.2f}) × 100 | **{f"${max_profit_c:.2f}" if max_profit_c is not None else "—"}** |
| **IV/HV Ratio** | {f"{float(r['iv_pct']):.1f}% IV" if pd.notna(r.get("iv_pct")) else "IV?"} / {f"{hv:.1f}% HV" if hv else "HV?"} | **{f"{iv_hv_ratio:.2f}" if iv_hv_ratio is not None else "—"}** |
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

- Verkauft für: **${last_price:.2f}**
- Zurückkaufen bei: **${close_50pct:.2f}** (buy-to-close)
- Gewinn: **${round(last_price - close_50pct, 2):.2f} pro Aktie** in ≤ {dte} Tagen → dann Kapital in die nächste Chance.
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
