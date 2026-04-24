import logging
import os
import streamlit as st
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.iron_condor_calculation import get_page_iron_condors
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
import pandas as pd

# Setup logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))

# Constants
DEFAULT_SHOW_MONTHLY = True
DEFAULT_SHOW_WEEKLY = False
DEFAULT_SHOW_DAILY = False
DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE = True
DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION = True
DEFAULT_DELTA_TARGET = 0.15
DEFAULT_SPREAD_WIDTH = 5
DEFAULT_MIN_DAY_VOLUME = 20
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_IV_RANK = 0
DEFAULT_MIN_SELL_IV = 0.3
DEFAULT_MAX_SELL_IV = 0.9
DEFAULT_MIN_MAX_PROFIT = 100.0

st.title("Iron Condors")

# Default values mapping for UI utils
DEFAULTS = {
    'ic_show_monthly': DEFAULT_SHOW_MONTHLY,
    'ic_show_weekly': DEFAULT_SHOW_WEEKLY,
    'ic_show_daily': DEFAULT_SHOW_DAILY,
    'ic_show_only_positiv_expected_value': DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE,
    'ic_show_only_spreads_with_no_earnings_till_expiration': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION,
    'ic_delta_put': DEFAULT_DELTA_TARGET,
    'ic_delta_call': DEFAULT_DELTA_TARGET,
    'ic_width_put': DEFAULT_SPREAD_WIDTH,
    'ic_width_call': DEFAULT_SPREAD_WIDTH,
    'ic_min_sell_iv': DEFAULT_MIN_SELL_IV,
    'ic_max_sell_iv': DEFAULT_MAX_SELL_IV,
    'ic_min_max_profit': DEFAULT_MIN_MAX_PROFIT
}

init_session_state(DEFAULTS)


def reset_to_defaults():
    ui_reset(DEFAULTS)


def clear_all_filters():
    st.session_state.ic_show_monthly = True
    st.session_state.ic_show_weekly = True
    st.session_state.ic_show_daily = True
    st.session_state.ic_show_only_positiv_expected_value = False
    st.session_state.ic_show_only_spreads_with_no_earnings_till_expiration = False
    st.session_state.ic_min_sell_iv = 0.0
    st.session_state.ic_max_sell_iv = 999.0
    st.session_state.ic_min_max_profit = 0.0

with st.expander("Configuration and Filters", expanded=True):
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, use_container_width=True)
    with btn_col2:
        st.button("Clear All Filters (Show All)", on_click=clear_all_filters, use_container_width=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_into_dataframe(sql_file_path=sql_file_path)
        
        # Filter dates_df based on checkbox states
        filtered_dates_df = filter_by_expiration_type(
            dates_df,
            'expiration_date',
            st.session_state.ic_show_monthly,
            st.session_state.ic_show_weekly,
            st.session_state.ic_show_daily
        )

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
            
        exp_put = st.selectbox("Put Expiration", dte_labels, index=0)
        exp_call = st.selectbox("Call Expiration", dte_labels, index=0)
        
        expiration_date_put = str(filtered_dates_df.iloc[dte_labels.index(exp_put)]['expiration_date'])
        expiration_date_call = str(filtered_dates_df.iloc[dte_labels.index(exp_call)]['expiration_date'])

    with col2:
        st.number_input("Put Delta Target", 0.0, 1.0, step=0.01, key="ic_delta_put")
        st.number_input("Call Delta Target", 0.0, 1.0, step=0.01, key="ic_delta_call")

    with col3:
        st.number_input("Put Spread Width", 1, 50, step=1, key="ic_width_put")
        st.number_input("Call Spread Width", 1, 50, step=1, key="ic_width_call")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.checkbox("Show Monthly", key="ic_show_monthly")
    with col5:
        st.checkbox("Show Weekly", key="ic_show_weekly")
    with col6:
        st.checkbox("Show Daily", key="ic_show_daily")

    col7, col8, col9 = st.columns(3)
    with col7:
        min_day_volume = st.number_input("Min Day Volume", 0, value=DEFAULT_MIN_DAY_VOLUME)
    with col8:
        min_open_interest = st.number_input("Min Open Interest", 0, value=DEFAULT_MIN_OPEN_INTEREST)
    with col9:
        min_iv_rank = st.number_input("Min IV Rank", 0, 100, value=DEFAULT_MIN_IV_RANK)

    col10, col11, col12 = st.columns(3)
    with col10:
        st.number_input("Min Sell IV", 0.0, step=0.05, format="%.2f", key="ic_min_sell_iv")
    with col11:
        st.number_input("Max Sell IV", 0.0, step=0.05, format="%.2f", key="ic_max_sell_iv")
    with col12:
        st.number_input("Min Max Profit", 0.0, step=1.0, format="%.2f", key="ic_min_max_profit")

    col13, col14 = st.columns(2)
    with col13:
        st.checkbox("Show only positive expected value", key="ic_show_only_positiv_expected_value")
    with col14:
        st.checkbox("Show only spreads with no earnings till expiration", key="ic_show_only_spreads_with_no_earnings_till_expiration")

with st.spinner("Calculating Iron Condors..."):
    common_params = {
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": 0
    }
    
    sql_query_path = PATH_DATABASE_QUERY_FOLDER / 'iron_condor_input.sql'
    
    # Get Put Spreads
    put_params = {**common_params, "expiration_date": expiration_date_put, "option_type": "put", "delta_target": st.session_state.ic_delta_put, "spread_width": st.session_state.ic_width_put}
    put_df = select_into_dataframe(sql_file_path=sql_query_path, params=put_params)
    
    # Get Call Spreads
    call_params = {**common_params, "expiration_date": expiration_date_call, "option_type": "call", "delta_target": st.session_state.ic_delta_call, "spread_width": st.session_state.ic_width_call}
    call_df = select_into_dataframe(sql_file_path=sql_query_path, params=call_params)
    
    ic_df = get_page_iron_condors(put_df, call_df)

if not ic_df.empty:
    # Apply filters
    # 1. Min max profit
    ic_df = ic_df[ic_df['max_profit'] >= st.session_state.ic_min_max_profit]
    
    # 2. Only positive expected value
    if st.session_state.ic_show_only_positiv_expected_value:
        ic_df = ic_df[ic_df['expected_value'] >= 0]
        
    # 3. Only spreads with no earnings till expiration
    if st.session_state.ic_show_only_spreads_with_no_earnings_till_expiration:
        today = pd.Timestamp.now().normalize()
        # For IC, we check if earnings are between today and EITHER of the expiration dates
        ic_df['expiration_date_put'] = pd.to_datetime(ic_df['expiration_date_put'])
        ic_df['expiration_date_call'] = pd.to_datetime(ic_df['expiration_date_call'])
        ic_df['earnings_date'] = pd.to_datetime(ic_df['earnings_date'])
        
        ic_df = ic_df[
            ~(
                (ic_df['earnings_date'] > today) & 
                (
                    (ic_df['earnings_date'] < ic_df['expiration_date_put']) | 
                    (ic_df['earnings_date'] < ic_df['expiration_date_call'])
                )
            )
        ]
        
    # 4. Sell IV filters (using the sell_iv column which should be the average or one of the legs)
    # Based on spreads page, it uses sell_iv. In IC we might have two sell legs.
    # Let's check if sell_iv exists in ic_df. In iron_condor_calculation.py it is calculated as (put_sell_iv + call_sell_iv) / 2
    if 'sell_iv' in ic_df.columns:
        ic_df = ic_df[ic_df['sell_iv'] >= st.session_state.ic_min_sell_iv]
        ic_df = ic_df[ic_df['sell_iv'] <= st.session_state.ic_max_sell_iv]

    # Format earnings date for display
    if not ic_df.empty:
        ic_df['earnings_date'] = pd.to_datetime(ic_df['earnings_date']).dt.strftime('%d.%m.%Y')
        ic_df.reset_index(drop=True, inplace=True)

if not ic_df.empty:
    st.markdown(f"### {len(ic_df)} Results")
    
    column_config = {
        "optionstrat_url": st.column_config.LinkColumn(label="", help="OptionStrat", display_text="🎯")
    }
    
    page_display_dataframe(ic_df, page='iron_condors', symbol_column='symbol', column_config=column_config)
else:
    st.warning("No results found for the selected criteria.")
