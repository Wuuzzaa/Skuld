"""Covered Call Screener - PowerOptions Style.

ITM Covered Calls mit Berechnung von Assigned Return, Annualized Return,
Downside Protection und Net Debit. Filtert nach Liquidität, Earnings und Technik.
"""

import logging
import os
import streamlit as st
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.covered_call_calculation import calc_covered_calls, get_page_covered_calls
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.utils.option_utils import get_expiration_type

# Ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# Setup logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Constants for default values
DEFAULT_SHOW_MONTHLY = True
DEFAULT_SHOW_WEEKLY = False
DEFAULT_SHOW_DAILY = False
DEFAULT_DELTA_TARGET = 0.6
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_VOLUME = 10
DEFAULT_MAX_PER_SYMBOL = 3
DEFAULT_MIN_ANNUALIZED = 0.10
DEFAULT_MIN_DOWNSIDE = 0.02
DEFAULT_EARNINGS_FILTER = True
DEFAULT_ABOVE_MA20 = False
DEFAULT_ABOVE_MA50 = False

# Page header
st.title("Covered Calls")
st.caption("PowerOptions-Style ITM Covered Call Screener")

# Default values mapping for UI utils
DEFAULTS = {
    'cc_show_monthly': DEFAULT_SHOW_MONTHLY,
    'cc_show_weekly': DEFAULT_SHOW_WEEKLY,
    'cc_show_daily': DEFAULT_SHOW_DAILY,
    'cc_delta_target': DEFAULT_DELTA_TARGET,
    'cc_min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'cc_min_volume': DEFAULT_MIN_VOLUME,
    'cc_max_per_symbol': DEFAULT_MAX_PER_SYMBOL,
    'cc_min_annualized': DEFAULT_MIN_ANNUALIZED,
    'cc_min_downside': DEFAULT_MIN_DOWNSIDE,
    'cc_earnings_filter': DEFAULT_EARNINGS_FILTER,
    'cc_above_ma20': DEFAULT_ABOVE_MA20,
    'cc_above_ma50': DEFAULT_ABOVE_MA50,
}

init_session_state(DEFAULTS)


def reset_to_defaults():
    ui_reset(DEFAULTS)


# Filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    st.button("Reset to Defaults", on_click=reset_to_defaults)

    # First row: Expiration + Delta Target + Max per Symbol
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_into_dataframe(sql_file_path=sql_file_path)

        # Filter dates_df based on checkbox states
        filtered_dates_df = filter_by_expiration_type(
            dates_df,
            'expiration_date',
            st.session_state.cc_show_monthly,
            st.session_state.cc_show_weekly,
            st.session_state.cc_show_daily
        )

        # DTE labels
        dte_labels = [
            (
                f"{int(row['days_to_expiration'])} DTE - "
                f"{pd.to_datetime(row['expiration_date']).strftime('%A')}  "
                f"{row['expiration_date']} - "
                f"{get_expiration_type(row['expiration_date'])}"
            )
            for _, row in filtered_dates_df.iterrows()
        ]

        if not dte_labels:
            st.warning("No expiration dates match the selected filters.")
            st.stop()

        selected_label = st.selectbox("Expiration Date", dte_labels, index=min(1, len(dte_labels) - 1))
        selected_index = dte_labels.index(selected_label)
        expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']

    with col2:
        delta_target = st.number_input(
            "Delta Target (ITM)",
            min_value=0.3,
            max_value=0.95,
            step=0.05,
            key="cc_delta_target",
            help="Target delta for ITM calls. Higher = deeper ITM, more protection."
        )

    with col3:
        max_per_symbol = st.number_input(
            "Max per Symbol",
            min_value=1,
            max_value=10,
            step=1,
            key="cc_max_per_symbol",
            help="Maximum number of strikes per symbol (ranked by delta proximity)."
        )

    with col4:
        min_open_interest = st.number_input(
            "Min Open Interest",
            min_value=0,
            step=50,
            key="cc_min_open_interest"
        )

    # Second row: Return filters + Volume
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        min_annualized = st.slider(
            "Min Annualized Return %",
            min_value=0,
            max_value=100,
            step=1,
            value=int(st.session_state.cc_min_annualized * 100),
            key="cc_min_annualized_slider",
            help="Minimum annualized return if assigned."
        ) / 100.0

    with col6:
        min_downside = st.slider(
            "Min Downside Protection %",
            min_value=0,
            max_value=30,
            step=1,
            value=int(st.session_state.cc_min_downside * 100),
            key="cc_min_downside_slider",
            help="Minimum premium as % of stock price (protection buffer)."
        ) / 100.0

    with col7:
        min_volume = st.number_input(
            "Min Volume",
            min_value=0,
            step=5,
            key="cc_min_volume"
        )

    with col8:
        st.checkbox("Show Monthly", key="cc_show_monthly")
        st.checkbox("Show Weekly", key="cc_show_weekly")

    # Third row: Toggles
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        earnings_filter = st.checkbox(
            "Exclude Earnings before Expiration",
            key="cc_earnings_filter",
            help="Remove stocks with earnings date before option expiration."
        )

    with col10:
        above_ma20 = st.checkbox(
            "Stock above 20-Day MA",
            key="cc_above_ma20",
            help="Only show stocks trading above their 20-day moving average."
        )

    with col11:
        above_ma50 = st.checkbox(
            "Stock above 50-Day MA",
            key="cc_above_ma50",
            help="Only show stocks trading above their 50-day moving average."
        )

    with col12:
        st.checkbox("Show Daily", key="cc_show_daily")


@st.cache_data
def _cached_query(sql_file_path, params):
    return select_into_dataframe(sql_file_path=sql_file_path, params=params)


@st.cache_data
def _cached_calc(df):
    return calc_covered_calls(df)


# Query and calculate
with st.spinner("Searching for covered call opportunities..."):
    params = {
        "expiration_date": expiration_date,
        "min_open_interest": min_open_interest,
        "max_per_symbol": max_per_symbol,
        "delta_target": delta_target,
    }

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'covered_calls.sql'
    df = _cached_query(sql_file_path=sql_file_path, params=params)
    logger.debug(f"Raw query returned {len(df)} rows")

    if df.empty:
        st.warning("No ITM calls found for selected expiration. Try a different date.")
        st.stop()

    # Calculate metrics
    cc_df = _cached_calc(df)
    logger.debug(f"After calculation: {len(cc_df)} rows")

# Apply display filters
filtered_df = get_page_covered_calls(
    cc_df,
    min_annualized=min_annualized,
    min_downside=min_downside,
    earnings_buffer_days=7 if earnings_filter else -9999,
    above_ma20=above_ma20,
    above_ma50=above_ma50,
    min_volume=min_volume,
)

st.markdown(f"### {len(filtered_df)} Results")

if filtered_df.empty:
    st.info("No results match the current filters. Try reducing Min Annualized Return or Min Downside Protection.")
    st.stop()

# Display table
event = page_display_dataframe(
    filtered_df,
    page=None,  # Uses default Claude prompt (generic analysis)
    symbol_column='symbol',
    on_select="rerun",
    selection_mode="single-row"
)

# Detail Panel
if not filtered_df.empty:
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        row = filtered_df.iloc[selected_idx]

        st.divider()
        st.markdown(f"### {row['symbol']} - {row.get('Company', 'N/A')}")

        # Key metrics
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Stock Price", f"${row['Stock']:.2f}")
            st.metric("Strike", f"${row['Strike']:.2f}")
        with col_m2:
            st.metric("Premium", f"${row['Premium']:.2f}")
            st.metric("Net Debit", f"${row['Net Debit']:.2f}")
        with col_m3:
            st.metric("Assigned Return", f"{row['Assigned %']:.1f}%")
            st.metric("Annualized Return", f"{row['Annual %']:.1f}%")
        with col_m4:
            st.metric("Downside Protection", f"{row['Protection %']:.1f}%")
            st.metric("ITM Depth", f"{row['ITM %']:.1f}%")

        # Investment per contract (100 shares)
        st.markdown("#### 💰 Per Contract (100 Shares)")
        col_inv1, col_inv2, col_inv3, col_inv4 = st.columns(4)
        with col_inv1:
            st.metric("Investment (100 × Stock)", f"${row.get('Investment', 0):,.0f}")
        with col_inv2:
            st.metric("Premium Income", f"${row.get('Prem Income', 0):,.0f}")
        with col_inv3:
            st.metric("Net Cost (after Premium)", f"${row.get('Net Cost', 0):,.0f}")
        with col_inv4:
            st.metric("Max Profit (if assigned)", f"${row.get('Max Profit', 0):,.0f}")

        # Additional info
        col_i1, col_i2, col_i3 = st.columns(3)
        with col_i1:
            st.write(f"**Delta:** {row['delta']:.3f}")
            st.write(f"**IV:** {row['iv']:.1%}" if pd.notnull(row.get('iv')) else "**IV:** N/A")
        with col_i2:
            st.write(f"**Open Interest:** {int(row['OI']):,}")
            st.write(f"**Volume:** {int(row['Vol']):,}")
        with col_i3:
            sector = row.get('company_sector', 'N/A')
            st.write(f"**Sector:** {sector}")
            earnings = row.get('earnings_date_next')
            if pd.notnull(earnings):
                st.write(f"**Next Earnings:** {earnings}")
            else:
                st.write("**Next Earnings:** N/A")

        # Links
        st.markdown("#### Links")
        link_col1, link_col2, link_col3, link_col4 = st.columns(4)
        with link_col1:
            st.link_button("TradingView", f"https://www.tradingview.com/symbols/{row['symbol']}/", use_container_width=True)
        with link_col2:
            st.link_button("Chart", f"https://www.tradingview.com/chart/?symbol={row['symbol']}", use_container_width=True)
        with link_col3:
            st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{row['symbol']}", use_container_width=True)
        with link_col4:
            if 'Claude' in row and pd.notnull(row.get('Claude')):
                st.link_button("Claude AI", row['Claude'], use_container_width=True)

    else:
        st.caption("💡 Klicke auf eine Zeile, um Details zu sehen.")

# Footer info
st.divider()
with st.expander("📖 PowerOptions Methodik", expanded=False):
    st.markdown("""
**Covered Call (Buy-Write):** Aktie kaufen + ITM Call verkaufen.

**Kennzahlen:**
- **Net Debit** = Aktienkurs − Premium (effektiver Einstiegspreis)
- **Assigned Return** = (Strike + Premium − Aktienkurs) / Net Debit (Rendite bei Ausübung)
- **Annualized Return** = Assigned Return × (365 / DTE) (auf ein Jahr hochgerechnet)
- **Downside Protection** = Premium / Aktienkurs (Puffer nach unten in %)
- **ITM Depth** = (Aktienkurs − Strike) / Aktienkurs (wie tief im Geld)

**Filter-Empfehlung (PowerOptions-Style):**
- Annualized Return ≥ 10-15%
- Downside Protection ≥ 2-5%
- Open Interest ≥ 100
- Keine Earnings vor Expiration
- Aktie über 20/50-Day MA (Aufwärtstrend)

**Vorteil ITM Calls:** Höhere Downside Protection als OTM, weniger Richtungsrisiko.
Nachteil: Geringerer maximaler Gewinn (auf Strike gekappt).
    """)
