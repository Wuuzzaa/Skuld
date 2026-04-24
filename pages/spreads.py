import logging
import os
import streamlit as st
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER
from pages.documentation_text.spreads_page_doc import get_spreads_documentation
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.spreads_calculation import get_page_spreads
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type

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
DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE = True
DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION = True
DEFAULT_DELTA_TARGET = 0.2
DEFAULT_SPREAD_WIDTH = 5
DEFAULT_OPTION_TYPE = "put"
DEFAULT_MIN_DAY_VOLUME = 20
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_SELL_IV = 0.3
DEFAULT_MAX_SELL_IV = 0.9
DEFAULT_MIN_MAX_PROFIT = 80.0
DEFAULT_MIN_IV_RANK = 0
DEFAULT_MIN_IV_PERCENTILE = 0

# Page header
st.title("Spreads")

# Default values mapping for UI utils
DEFAULTS = {
    'show_monthly': DEFAULT_SHOW_MONTHLY,
    'show_weekly': DEFAULT_SHOW_WEEKLY,
    'show_daily': DEFAULT_SHOW_DAILY,
    'show_only_positiv_expected_value': DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE,
    'show_only_spreads_with_no_earnings_till_expiration': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION,
    'delta_target': DEFAULT_DELTA_TARGET,
    'spread_width': DEFAULT_SPREAD_WIDTH,
    'option_type': DEFAULT_OPTION_TYPE,
    'min_day_volume': DEFAULT_MIN_DAY_VOLUME,
    'min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'min_sell_iv': DEFAULT_MIN_SELL_IV,
    'max_sell_iv': DEFAULT_MAX_SELL_IV,
    'min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'min_iv_rank': DEFAULT_MIN_IV_RANK,
    'min_iv_percentile': DEFAULT_MIN_IV_PERCENTILE
}

init_session_state(DEFAULTS)


def reset_to_defaults():
    ui_reset(DEFAULTS)


def clear_all_filters():
    """
    Clears all filters to show all possible results.
    """
    st.session_state.show_monthly = True
    st.session_state.show_weekly = True
    st.session_state.show_daily = True
    st.session_state.show_only_positiv_expected_value = False
    st.session_state.show_only_spreads_with_no_earnings_till_expiration = False
    st.session_state.min_day_volume = 0
    st.session_state.min_open_interest = 0
    st.session_state.min_sell_iv = 0.0
    st.session_state.max_sell_iv = 999.0
    st.session_state.min_max_profit = 0.0
    st.session_state.min_iv_rank = 0
    st.session_state.min_iv_percentile = 0


# Filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    # Action buttons
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, use_container_width=True)
    with btn_col2:
        st.button("Clear All Filters (Show All)", on_click=clear_all_filters, use_container_width=True)

    # First row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_into_dataframe(sql_file_path=sql_file_path)

        # Filter dates_df based on checkbox states
        filtered_dates_df = filter_by_expiration_type(
            dates_df, 
            'expiration_date', 
            st.session_state.show_monthly, 
            st.session_state.show_weekly, 
            st.session_state.show_daily
        )

        # DTE labels ("5 DTE - Friday 2026-01-16 - Monthly/Weekly/Daily")
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

        # Selectbox with DTE labels
        selected_label = st.selectbox("Expiration Date", dte_labels)

        # Extract selected expiration date from DTE label
        selected_index = dte_labels.index(selected_label)
        expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']
        logging.debug(f"Extracted selected expiration date: {expiration_date}")

    with col2:
        delta_target = st.number_input(
            "Delta Target",
            min_value=0.0,
            max_value=1.0,
            step=0.01,
            key="delta_target"
        )

    with col3:
        spread_width = st.number_input(
            "Spread Width",
            min_value=1,
            max_value=20,
            step=1,
            key="spread_width"
        )

    with col4:
        option_type = st.selectbox("Option Type", ["put", "call"], key="option_type")

    # Second row
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.checkbox("Show Monthly", key="show_monthly")

    with col6:
        st.checkbox("Show Weekly", key="show_weekly")

    with col7:
        st.checkbox("Show Daily", key="show_daily")

    with col8:
        st.checkbox(
            "Show only positive expected value",
            key="show_only_positiv_expected_value"
        )

    # Third row
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        min_day_volume = st.number_input(
            "Min dayvolume",
            min_value=0,
            step=1,
            key="min_day_volume"
        )

    with col10:
        min_open_interest = st.number_input(
            "Min Open Interest",
            min_value=0,
            step=100,
            key="min_open_interest"
        )

    with col11:
        min_sell_iv = st.number_input(
            "Min sell iv",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="min_sell_iv"
        )

    with col12:
        max_sell_iv = st.number_input(
            "Max sell iv",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="max_sell_iv"
        )

    # Fourth row
    col13, col14, col15, col16 = st.columns(4)

    with col13:
        st.checkbox(
            "Show only spreads with no earnings till expiration",
            key="show_only_spreads_with_no_earnings_till_expiration"
        )

    with col14:
        min_max_profit = st.number_input(
            "Min Max Profit",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="min_max_profit"
        )

    with col15:
        min_iv_rank = st.number_input(
            "Min iv rank",
            min_value=0,
            max_value=100,
            step=1,
            key="min_iv_rank"
        )

    with col16:
        min_iv_percentile = st.number_input(
            "Min iv percentile",
            min_value=0,
            max_value=100,
            step=1,
            key="min_iv_percentile"
        )

# Calculate the spread values with a loading indicator
with st.spinner("Calculating spreads..."):
    params = {
        "expiration_date": expiration_date,
        "option_type": option_type,
        "delta_target": delta_target,
        "min_open_interest": min_open_interest,
        "spread_width": spread_width,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile
    }

    logging.debug(f"Params for database query: {params}")

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path, params=params)
    logging.debug(f"Input data head: {df.head()}")

    spreads_df = get_page_spreads(df)
    logging.debug(f"Calculated spreads head: {spreads_df.head()}")

# Apply spread filters
filtered_df = spreads_df.copy()

# Min max profit
filtered_df = filtered_df[filtered_df['max_profit'] >= min_max_profit]

# Only positive expected value
if st.session_state.show_only_positiv_expected_value:
    filtered_df = filtered_df[filtered_df['expected_value'] >= 0]

# Only spreads with no earnings till expiration
today = pd.Timestamp.now().normalize()
expiration_date_ts = pd.Timestamp(expiration_date)

if st.session_state.show_only_spreads_with_no_earnings_till_expiration:
    filtered_df = filtered_df[
        ~(
                (filtered_df['earnings_date'] > today) &
                (filtered_df['earnings_date'] < expiration_date_ts)
        )
    ]

# Convert 'earnings_date' to datetime and format it
filtered_df['earnings_date'] = pd.to_datetime(filtered_df['earnings_date'])
filtered_df['earnings_date'] = filtered_df['earnings_date'].dt.strftime('%d.%m.%Y')

# Min sell IV
filtered_df = filtered_df[filtered_df['sell_iv'] >= min_sell_iv]

# Max sell IV
filtered_df = filtered_df[filtered_df['sell_iv'] <= max_sell_iv]

# Reset index to ensure the zebra style works on the dataframe
filtered_df.reset_index(drop=True, inplace=True)

# Pre-format columns that we want to show in details but not in the main table
# This ensures they are available in 'row' even after page_display_dataframe might have dropped them from display
# Actually page_display_dataframe creates a copy for display, so filtered_df remains intact.

st.markdown(f"### {len(filtered_df)} Results")

# Optionstrat URL configuration
column_config = {
    "optionstrat_url": st.column_config.LinkColumn(
        label="",
        help="OptionStrat",
        display_text="🎯",
    )
}

# Display final dataframe
event = page_display_dataframe(
    filtered_df, 
    page='spreads', 
    symbol_column='symbol', 
    column_config=column_config,
    on_select="rerun",
    selection_mode="single-row"
)

# Leg Details View
selected_rows = event.selection.rows if hasattr(event, "selection") else []
if selected_rows and not filtered_df.empty:
    selected_idx = selected_rows[0]
    row = filtered_df.iloc[selected_idx]

    st.divider()
    st.subheader(f"Details für {row['symbol']} {row['option_type'].capitalize()} Spread")

    # Create detailed table for legs
    legs_data = [
        {
            "Leg": f"Short {row['option_type'].capitalize()}",
            "Strike": row['sell_strike'],
            "Price": row['sell_last_option_price'],
            "Delta": row['sell_delta'],
            "IV": row['sell_iv'],
            "Theta": row['sell_theta'],
            "OI": row['sell_open_interest'],
            "Volume": row.get('sell_day_volume'),
            "Exp Move": row.get('sell_expected_move')
        },
        {
            "Leg": f"Long {row['option_type'].capitalize()}",
            "Strike": row['buy_strike'],
            "Price": row['buy_last_option_price'],
            "Delta": row['buy_delta'],
            "IV": row['buy_iv'],
            "Theta": row['buy_theta'],
            "OI": row['buy_open_interest'],
            "Volume": row.get('buy_day_volume'),
            "Exp Move": row.get('buy_expected_move')
        }
    ]
    
    details_df = pd.DataFrame(legs_data)
    st.table(details_df)
    
    # Additional Info
    st.markdown("#### Kennzahlen & Unternehmensinfos")
    st.write(f"**Unternehmen:** {row.get('Company', 'N/A')}")
    
    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    with col_info1:
        st.metric("Max Profit", f"${row['max_profit']:.2f}")
        st.metric("BPR", f"${row['bpr']:.2f}")
    with col_info2:
        st.metric("Expected Value", f"${row['expected_value']:.2f}")
        st.metric("APDI", f"{row['APDI']:.2f}%")
    with col_info3:
        st.metric("IV Rank", f"{row['iv_rank']:.1f}")
        st.metric("IV Percentile", f"{row['iv_percentile']:.1f}")
    with col_info4:
        st.metric("Hist. Vola (30d)", f"{row.get('historical_volatility_30d', 0)*100:.1f}%")
        st.write(f"**Sektor:** {row['company_sector']}")
        st.write(f"**Branche:** {row['company_industry']}")

    if 'analyst_mean_target' in row:
        st.write(f"**Analyst Kursziel:** ${row['analyst_mean_target']:.2f} (Aktuell: ${row['close']:.2f})")

    # External Links
    st.markdown("#### Links")
    link_col1, link_col2, link_col3, link_col4 = st.columns(4)
    with link_col1:
        st.link_button("TradingView", f"https://www.tradingview.com/symbols/{row['symbol']}/", use_container_width=True)
    with link_col2:
        st.link_button("Finviz", f"https://finviz.com/quote.ashx?t={row['symbol']}", use_container_width=True)
    with link_col3:
        st.link_button("Seeking Alpha", f"https://seekingalpha.com/symbol/{row['symbol']}", use_container_width=True)
    with link_col4:
        st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{row['symbol']}", use_container_width=True)

else:
    st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die Details der einzelnen Legs zu sehen.")

# Show documentation
with st.expander("📖 Documentation - Fields Overview", expanded=False):
    st.markdown(get_spreads_documentation())