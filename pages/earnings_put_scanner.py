"""
Earnings Put Scanner
====================
A tool for identifying short-term cash-secured put opportunities around earnings
announcements, based on the principle that implied volatility collapses after
earnings are released ("IV crush").

Strategy Overview
-----------------
1. Find stocks with earnings announcements in the current week.
2. Filter for quality: market cap > $2B, price $15–$250, liquid options market.
3. Sell a weekly put with a strike BELOW the expected move range.
4. Close the next morning at 90% profit, or within 60 minutes of open at breakeven.

Why it works
------------
- Before earnings, options are overpriced due to uncertainty (high IV).
- After earnings, IV collapses because the uncertainty is resolved.
- You profit from both time decay and IV crush — not from predicting direction.

Risk
----
Worst case: stock gaps below your strike and you get assigned 100 shares at strike
price. Manage by selling a covered call on the assigned shares to recover cost basis.

Data sources
------------
All data is read from OptionDataMerged (PostgreSQL), which combines option chains,
fundamental data, IV metrics, and expected move estimates into a single view.
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

# ── Page header ──────────────────────────────────────────────────────────────
st.title("Earnings Put Scanner")
st.caption(
    "Sell weekly puts below the expected move range before earnings — "
    "profit from IV crush the next morning."
)

with st.expander("How this strategy works", expanded=False):
    st.markdown("""
    **Setup (once per earnings season)**
    - Earnings seasons: Q1 mid-April, Q2 mid-July, Q3 mid-October, Q4 mid-January
    - Filter criteria applied automatically: MarketCap > $2B, Price $15–$250, liquid options

    **Weekly workflow**

    | Step | Action |
    |------|--------|
    | 1 | Scan for stocks with earnings this week (table below) |
    | 2 | Check the Expected Move column — this is your safety buffer |
    | 3 | Find a put strike **below** `Current Price − Expected Move` |
    | 4 | Verify: Premium ≥ 1% of strike, IV Rank > 50% (options are expensive) |
    | 5 | Sell the put — target weekly expiry in the same week as earnings |
    | 6 | **Next morning:** close at 90% profit (buy back for 10% of premium received) |
    | 7 | If 90% not possible: close 60 min after open at any small gain |

    **Exit rules**
    - Close at 90% profit → e.g. sold for $1.30, buy back at $0.13
    - Close 60 min after open at breakeven if target not reached
    - Never hold through expiry unless you accept assignment

    **Worst case — Assignment**
    Stock gaps below your strike. You buy 100 shares at strike price.
    Recovery: sell a covered call on the assigned shares ("Get Paid to Wait").
    """)

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("eps_candidates_df", None),
    ("eps_selected_symbol", None),
    ("eps_puts_df", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Filter controls ───────────────────────────────────────────────────────────
st.subheader("Scanner Filters")

col1, col2, col3, col4 = st.columns([1.5, 1.5, 1.5, 1])

with col1:
    days_ahead = st.selectbox(
        "Earnings within",
        options=[3, 5, 7, 10, 14, 21, 30, 45, 60],
        index=2,
        format_func=lambda x: f"{x} days",
        key="eps_days_ahead",
    )
with col2:
    require_dividend = st.selectbox(
        "Dividend Filter",
        options=["All", "Dividend Payers Only"],
        index=0,
        key="eps_div_filter",
    )
with col3:
    max_pe = st.number_input(
        "Max P/E Ratio",
        min_value=1,
        max_value=500,
        value=100,
        step=5,
        key="eps_max_pe",
    )
with col4:
    min_iv_rank = st.number_input(
        "Min IV Rank %",
        min_value=0,
        max_value=100,
        value=40,
        step=5,
        key="eps_min_iv_rank",
    )

scan_btn = st.button("Scan for Candidates", type="primary")

# ── Load candidates ───────────────────────────────────────────────────────────
if scan_btn:
    with st.spinner("Scanning for earnings candidates..."):
        try:
            sql_path = PATH_DATABASE_QUERY_FOLDER / "earnings_put_scanner.sql"
            raw_df = select_into_dataframe(
                sql_file_path=sql_path,
                params={"days_ahead": days_ahead},
            )

            if raw_df.empty:
                st.warning("No candidates found. Try increasing the earnings window.")
                st.session_state["eps_candidates_df"] = None
            else:
                df = raw_df.copy()

                # Numeric coercion
                for col in ["trailing_pe", "iv_rank", "iv_percentile", "live_stock_price",
                            "expected_move", "expected_move_pct", "market_cap", "avg_volume"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")

                # Apply filters
                if require_dividend == "Dividend Payers Only":
                    df = df[df["dividend_classification"].notna() &
                            (df["dividend_classification"] != "")]

                if max_pe < 500:
                    df = df[
                        df["trailing_pe"].isna() | (df["trailing_pe"] <= max_pe)
                    ]

                df = df[df["iv_rank"].isna() | (df["iv_rank"] >= min_iv_rank)]

                if df.empty:
                    st.warning("All candidates were filtered out. Try relaxing the filters.")
                    st.session_state["eps_candidates_df"] = None
                else:
                    df = df.sort_values(["days_to_earnings", "iv_rank"],
                                        ascending=[True, False])
                    st.session_state["eps_candidates_df"] = df
                    st.session_state["eps_selected_symbol"] = None
                    st.session_state["eps_puts_df"] = None
                    st.rerun()

        except Exception as e:
            st.error(f"Error loading candidates: {e}")
            logger.error(e, exc_info=True)

# ── Candidate table ────────────────────────────────────────────────────────────
if st.session_state["eps_candidates_df"] is not None:
    df = st.session_state["eps_candidates_df"].copy()

    st.divider()
    st.subheader(f"Earnings Candidates — {len(df)} found")
    st.caption("Click a row to see available put options for that symbol.")

    # Build display table
    def _fmt_market_cap(v):
        if pd.isna(v):
            return "—"
        if v >= 1e12:
            return f"${v/1e12:.1f}T"
        if v >= 1e9:
            return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"

    def _iv_rank_signal(row):
        iv = row.get("iv_rank", None)
        if pd.isna(iv):
            return "—"
        if iv >= 60:
            return f"High {iv:.0f}%"
        if iv >= 40:
            return f"Mid {iv:.0f}%"
        return f"Low {iv:.0f}%"

    display_df = pd.DataFrame({
        "Symbol":        df["symbol"],
        "Earnings":      df["earnings_date"].astype(str),
        "Days":          df["days_to_earnings"].astype("Int64"),
        "Price ($)":     df["live_stock_price"].apply(
                             lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
        "Exp. Move":     df.apply(
                             lambda r: f"±{r['expected_move']:.2f} ({r['expected_move_pct']:.1f}%)"
                             if pd.notna(r.get("expected_move")) else "—", axis=1),
        "IV Rank":       df.apply(_iv_rank_signal, axis=1),
        "MarketCap":     df["market_cap"].apply(_fmt_market_cap),
        "P/E":           df["trailing_pe"].apply(
                             lambda v: f"{v:.1f}" if pd.notna(v) else "—"),
        "Dividend":      df["dividend_classification"].fillna("—"),
    })

    event = st.dataframe(
        display_df,
        use_container_width=True,
        height=min(600, 40 + 35 * len(display_df)),
        selection_mode="single-row",
        on_select="rerun",
        key="eps_candidate_table",
    )

    # Handle row selection
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        selected_symbol = df.iloc[selected_idx]["symbol"]

        if selected_symbol != st.session_state.get("eps_selected_symbol"):
            st.session_state["eps_selected_symbol"] = selected_symbol
            st.session_state["eps_puts_df"] = None
            st.rerun()

# ── Put candidates for selected symbol ────────────────────────────────────────
if st.session_state.get("eps_selected_symbol"):
    symbol = st.session_state["eps_selected_symbol"]
    candidates_df = st.session_state["eps_candidates_df"]
    symbol_row = candidates_df[candidates_df["symbol"] == symbol].iloc[0]

    live_price = symbol_row.get("live_stock_price")
    expected_move = symbol_row.get("expected_move")
    earnings_date = symbol_row.get("earnings_date")

    # Safety threshold: strike must be below price - expected_move
    if pd.notna(live_price) and pd.notna(expected_move):
        safety_threshold = float(live_price) - float(expected_move)
    else:
        safety_threshold = None

    st.divider()
    st.subheader(f"Put Candidates — {symbol}")

    # Info banner
    info_cols = st.columns(4)
    with info_cols[0]:
        st.metric("Current Price", f"${float(live_price):.2f}" if pd.notna(live_price) else "—")
    with info_cols[1]:
        st.metric("Expected Move",
                  f"±${float(expected_move):.2f}" if pd.notna(expected_move) else "—",
                  help="Strike should be BELOW this threshold")
    with info_cols[2]:
        st.metric("Safety Strike Threshold",
                  f"${safety_threshold:.2f}" if safety_threshold else "—",
                  help="Sell puts with strike below this level")
    with info_cols[3]:
        st.metric("Earnings Date", str(earnings_date) if earnings_date else "—")

    # Filter controls for puts
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        min_oi = st.number_input(
            "Min Open Interest",
            min_value=0,
            value=50,
            step=25,
            key="eps_min_oi",
        )
    with p_col2:
        min_premium_pct = st.number_input(
            "Min Premium % of Strike",
            min_value=0.0,
            max_value=10.0,
            value=1.0,
            step=0.1,
            format="%.1f",
            key="eps_min_premium_pct",
        )

    # Load puts
    if st.session_state["eps_puts_df"] is None:
        with st.spinner(f"Loading put options for {symbol}..."):
            try:
                sql_path = PATH_DATABASE_QUERY_FOLDER / "earnings_put_candidates.sql"
                puts_df = select_into_dataframe(
                    sql_file_path=sql_path,
                    params={"symbol": symbol, "min_oi": min_oi},
                )
                st.session_state["eps_puts_df"] = puts_df
            except Exception as e:
                st.error(f"Error loading puts: {e}")
                logger.error(e, exc_info=True)

    puts_df = st.session_state.get("eps_puts_df")

    if puts_df is not None and not puts_df.empty:
        df_puts = puts_df.copy()

        for col in ["strike_price", "premium_option_price", "premium_pct",
                    "open_interest", "implied_volatility", "greeks_delta",
                    "live_stock_price", "expected_move"]:
            if col in df_puts.columns:
                df_puts[col] = pd.to_numeric(df_puts[col], errors="coerce")

        # Apply filters
        if min_oi > 0:
            df_puts = df_puts[df_puts["open_interest"] >= min_oi]

        df_puts = df_puts[df_puts["premium_pct"] >= min_premium_pct]

        # Flag: is strike safely below expected move threshold?
        if safety_threshold:
            df_puts["below_threshold"] = df_puts["strike_price"] < safety_threshold
        else:
            df_puts["below_threshold"] = False

        if df_puts.empty:
            st.info("No puts match the current filters. Try lowering Min OI or Min Premium %.")
        else:
            # Profit target calculator: 90% of premium
            df_puts["close_at_90pct"] = (df_puts["premium_option_price"] * 0.10).round(2)

            # Build display table
            disp = pd.DataFrame({
                "Expiry":        df_puts["expiration_date"].astype(str),
                "DTE":           df_puts["days_to_expiration"].astype("Int64"),
                "Strike ($)":    df_puts["strike_price"].apply(lambda v: f"{v:.1f}"),
                "Below Thresh.": df_puts["below_threshold"].apply(
                                     lambda v: "Safe" if v else "Inside"),
                "Premium ($)":   df_puts["premium_option_price"].apply(
                                     lambda v: f"{v:.2f}" if pd.notna(v) else "—"),
                "Premium %":     df_puts["premium_pct"].apply(
                                     lambda v: f"{v:.2f}%" if pd.notna(v) else "—"),
                "Close @ 90%":   df_puts["close_at_90pct"].apply(
                                     lambda v: f"${v:.2f}"),
                "OI":            df_puts["open_interest"].apply(
                                     lambda v: f"{int(v):,}" if pd.notna(v) else "—"),
                "Delta":         df_puts["greeks_delta"].apply(
                                     lambda v: f"{v:.3f}" if pd.notna(v) else "—"),
                "IV":            df_puts["implied_volatility"].apply(
                                     lambda v: f"{v*100:.1f}%" if pd.notna(v) else "—"),
            })

            # Highlight safe rows (below expected move)
            def _highlight_rows(row):
                if row["Below Thresh."] == "Safe":
                    return ["background-color: rgba(20, 83, 45, 0.25)"] * len(row)
                return [""] * len(row)

            styled = disp.style.apply(_highlight_rows, axis=1).hide(axis="index")

            st.markdown(f"**{len(disp)} puts found** — green rows are safely below expected move")
            st.dataframe(styled, use_container_width=True,
                         height=min(600, 40 + 35 * len(disp)))

            # Quick reference box
            st.info(
                f"**Trade checklist for {symbol}:**  \n"
                f"1. Choose a Safe row with Premium % >= {min_premium_pct:.1f}%  \n"
                f"2. Sell the put — collect premium  \n"
                f"3. Next morning: buy back at **Close @ 90%** value  \n"
                f"4. If not filled within 60 min of open → close at market"
            )
    elif puts_df is not None:
        st.info(f"No weekly puts found for {symbol} with the current filters.")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "Earnings Put Scanner — IV Crush Strategy | "
    "Data: OptionDataMerged | "
    "Strategy basis: RadioActive Trading / PowerX methodology"
)
