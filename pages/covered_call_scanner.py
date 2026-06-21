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

col4, col5, col6 = st.columns(3)
with col4:
    min_annualized = st.number_input(
        "Min Annualized Return %",
        min_value=0, max_value=200,
        value=30, step=5,
        key="cc_min_ann",
    )
with col5:
    max_annualized = st.number_input(
        "Max Annualized Return %",
        min_value=10, max_value=1000,
        value=30, step=10,
        key="cc_max_ann",
        help="Cap utopian values. Anything above ~100% is usually a data artefact or illiquid option.",
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
        value=10, step=1,
        key="cc_min_downside",
        help="Filter out positions with insufficient downside buffer.",
    )
with col9:
    max_annualized_2 = None  # placeholder — layout symmetry

col10, col11, col12 = st.columns(3)
with col10:
    min_iv_rank = st.number_input(
        "Min IV Rank",
        min_value=0, max_value=100,
        value=50, step=5,
        key="cc_min_iv_rank",
        help="PowerOptions uses IV Rank >= 50 to ensure options are expensive enough to sell.",
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
    pass

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
                    df = df[df["premium"] >= min_premium]

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
        "Symbol":        df["symbol"],
        "Sector":        df["company_sector"].fillna("—"),
        "Stock ($)":     df["stock_price"].apply(lambda v: f"{v:.2f}"),
        "Strike ($)":    df["strike_price"].apply(lambda v: f"{v:.2f}"),
        "Premium ($)":   df["premium"].apply(lambda v: f"{v:.2f}"),
        "Investment ($)": df["stock_price"].apply(lambda v: f"{v * 100:,.0f}"),
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

        # Metrics row
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Net Debit", f"${net_debit:.2f}", help="Your real cost per share")
        m2.metric("Assigned Return", f"{assigned_ret:.2f}%", help="Profit if called away at expiry")
        m3.metric("Annualized Return", f"{annualized:.1f}%")
        m4.metric("Downside Protection", f"{protection:.1f}%", help="Premium / Stock Price")

        st.markdown(f"""
**How the metrics are calculated**

| | Calculation | Result |
|---|---|---|
| Net Debit | ${stock:.2f} (stock) − ${premium:.2f} (premium) | **${net_debit:.2f}** |
| Assigned Return | (${strike:.2f} − ${net_debit:.2f}) / ${net_debit:.2f} × 100 | **{assigned_ret:.2f}%** |
| Annualized Return | {assigned_ret:.2f}% / {dte} days × 365 | **{annualized:.1f}%** |
| Downside Protection | ${premium:.2f} / ${stock:.2f} × 100 | **{protection:.1f}%** |

---

**Profit & Loss at expiry ({expiry})**

| Scenario | Stock at expiry | Result |
|---|---|---|
| Shares called away (best case) | Above ${strike:.2f} | +${max_profit:.2f} per contract (+{assigned_ret:.2f}%) |
| Breakeven | Exactly ${breakeven:.2f} | $0 |
| Below breakeven | Below ${breakeven:.2f} | Loss = (${breakeven:.2f} − stock price) × 100 |

---

**Early exit — 50% profit rule**

Standard best practice: close when premium drops to 50% of what you sold it for.

- Sold for: **${premium:.2f}**
- Close at: **${close_50pct:.2f}** (buy-to-close)
- Profit: **${round(premium - close_50pct, 2):.2f} per share** in {dte} days or less
- Then redeploy capital into the next opportunity

---

**Volatility**

{iv_comment}
{iv_hv_text}

---

**Earnings**

{earn_warning}

---

**Delta {delta_val:.3f} — what it means**

Delta of {delta_val:.3f} means the option moves ~${delta_val:.2f} for every $1 move in the stock.
Assignment probability at expiry is approximately **{delta_val*100:.0f}%**.
{"This is a deep ITM call — high probability of assignment. The strategy is essentially a fixed-return income trade." if delta_val >= 0.8 else "Moderate ITM — reasonable balance between premium and assignment probability."}
""")

    else:
        st.caption("Click a row to see detailed trade analysis and P&L breakdown.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "ITM Covered Call Scanner — PowerOptions MorningUpdate methodology | "
    "Data: OptionDataMerged + StockData"
)
