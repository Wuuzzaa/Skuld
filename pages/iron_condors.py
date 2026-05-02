import logging
import os
import streamlit as st
from config import PATH_DATABASE_QUERY_FOLDER, IV_CORRECTION_MODE
from pages.documentation_text.iron_condors_page_doc import get_iron_condor_documentation
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.iron_condor_calculation import get_page_iron_condors, calc_iron_condors
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.ui_strategy_display import display_strategy_details
from src.options_utils import OptionLeg, StrategyMetrics
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

# Management Defaults
DEFAULT_TAKE_PROFIT = 50
DEFAULT_STOP_LOSS = 200
DEFAULT_DTE_CLOSE = 21

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
    'ic_min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'ic_iv_correction': IV_CORRECTION_MODE,
    'ic_min_day_volume': DEFAULT_MIN_DAY_VOLUME,
    'ic_min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'ic_min_iv_rank': DEFAULT_MIN_IV_RANK,
    'ic_take_profit': DEFAULT_TAKE_PROFIT,
    'ic_stop_loss': DEFAULT_STOP_LOSS,
    'ic_dte_close': DEFAULT_DTE_CLOSE
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
    st.session_state.ic_min_day_volume = 0
    st.session_state.ic_min_open_interest = 0
    st.session_state.ic_min_iv_rank = 0
    st.session_state.ic_take_profit = 0
    st.session_state.ic_stop_loss = 500
    st.session_state.ic_dte_close = 0

with st.expander("Documentation"):
    st.markdown(get_iron_condor_documentation())

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
            
        exp_put = st.selectbox("Put Expiration", dte_labels, index=min(1, len(dte_labels)-1))
        exp_call = st.selectbox("Call Expiration", dte_labels, index=min(1, len(dte_labels)-1))
        
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
        st.number_input("Min Day Volume", 0, key="ic_min_day_volume")
    with col8:
        st.number_input("Min Open Interest", 0, key="ic_min_open_interest")
    with col9:
        st.number_input("Min IV Rank", 0, 100, key="ic_min_iv_rank")

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

    st.divider()
    col15, col16 = st.columns(2)
    with col15:
        iv_corr_input = st.text_input("IV Correction (auto, 0.0-1.0)", value=str(st.session_state.ic_iv_correction), key="ic_iv_correction_input")
        # Process input to match expected types (float or "auto")
        if iv_corr_input.lower() == "auto":
            st.session_state.ic_iv_correction = "auto"
        else:
            try:
                st.session_state.ic_iv_correction = float(iv_corr_input)
            except ValueError:
                st.error("Invalid IV Correction. Use 'auto' or a number.")
                st.session_state.ic_iv_correction = 0.0
    with col16:
        st.info("IV correction mode: 'auto' (Automatic), 0.0-1.0 (Manual reduction), 0.0 (No correction)")

    st.divider()
    st.markdown("### Management Strategy")
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        st.number_input("Take Profit %", min_value=0, max_value=500, step=10, key="ic_take_profit")
    with m_col2:
        st.number_input("Stop Loss %", min_value=0, max_value=500, step=10, key="ic_stop_loss")
    with m_col3:
        st.number_input("DTE Close", min_value=0, max_value=365, step=1, key="ic_dte_close")

@st.cache_data
def _cached_select_into_dataframe(sql_file_path, params):
    return select_into_dataframe(sql_file_path=sql_file_path, params=params)

@st.cache_data
def _cached_calc_iron_condors(put_df, call_df, iv_correction, take_profit=None, stop_loss=None, dte_close=None):
    return calc_iron_condors(put_df, call_df, iv_correction=iv_correction,
                            take_profit=take_profit, stop_loss=stop_loss, dte_close=dte_close)

@st.cache_data
def _cached_get_page_iron_condors(ic_df_raw, iv_correction, take_profit=None, stop_loss=None, dte_close=None):
    return get_page_iron_condors(ic_df_raw, iv_correction=iv_correction,
                                 take_profit=take_profit, stop_loss=stop_loss, dte_close=dte_close)


with st.spinner("Calculating Iron Condors..."):
    common_params = {
        "min_open_interest": st.session_state.ic_min_open_interest,
        "min_day_volume": st.session_state.ic_min_day_volume,
        "min_iv_rank": st.session_state.ic_min_iv_rank,
        "min_iv_percentile": 0
    }
    
    sql_query_path = PATH_DATABASE_QUERY_FOLDER / 'iron_condor_input.sql'
    
    # Get Put Spreads
    put_params = {**common_params, "expiration_date": expiration_date_put, "option_type": "put", "delta_target": st.session_state.ic_delta_put, "spread_width": st.session_state.ic_width_put}
    put_df = _cached_select_into_dataframe(sql_file_path=sql_query_path, params=put_params)
    
    # Get Call Spreads
    call_params = {**common_params, "expiration_date": expiration_date_call, "option_type": "call", "delta_target": st.session_state.ic_delta_call, "spread_width": st.session_state.ic_width_call}
    call_df = _cached_select_into_dataframe(sql_file_path=sql_query_path, params=call_params)
    
    ic_df_raw = _cached_calc_iron_condors(
        put_df, call_df, st.session_state.ic_iv_correction,
        take_profit=st.session_state.ic_take_profit,
        stop_loss=st.session_state.ic_stop_loss,
        dte_close=st.session_state.ic_dte_close
    )
    ic_df = _cached_get_page_iron_condors(
        ic_df_raw, st.session_state.ic_iv_correction,
        take_profit=st.session_state.ic_take_profit,
        stop_loss=st.session_state.ic_stop_loss,
        dte_close=st.session_state.ic_dte_close
    )

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
    if 'sell_iv' in ic_df.columns:
        ic_df = ic_df[ic_df['sell_iv'] >= st.session_state.ic_min_sell_iv]
        ic_df = ic_df[ic_df['sell_iv'] <= st.session_state.ic_max_sell_iv]

    # Re-reset index after all filters are applied
    ic_df.reset_index(drop=True, inplace=True)

    # Format earnings date for display
    if not ic_df.empty:
        ic_df['earnings_date'] = pd.to_datetime(ic_df['earnings_date']).dt.strftime('%d.%m.%Y')

if not ic_df.empty:
    st.markdown(f"### {len(ic_df)} Results")
    
    column_config = {
        "optionstrat_url": st.column_config.LinkColumn(label="", help="OptionStrat", display_text="🎯")
    }
    
    event = page_display_dataframe(
        ic_df, 
        page='iron_condors', 
        symbol_column='symbol', 
        column_config=column_config,
        on_select="rerun",
        selection_mode="single-row"
    )

    # Leg Details View
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows and not ic_df.empty:
        selected_idx = selected_rows[0]
        row = ic_df.iloc[selected_idx]

        st.divider()
        st.info("💡 Klicke auf eine Zeile in der Tabelle, um Details wie EV (Managed) und Simulations-Griechen zu sehen.")
        
        legs = [
            OptionLeg(
                strike=row['sell_strike_put'], premium=row['sell_last_option_price_put'], is_call=False, is_long=False,
                delta=row.get('sell_delta_put'), iv=row.get('sell_iv_put'), theta=row.get('sell_theta_put'),
                oi=row.get('sell_open_interest_put'), volume=row.get('sell_day_volume_put'),
                expected_move=row.get('sell_expected_move_put')
            ),
            OptionLeg(
                strike=row['buy_strike_put'], premium=row['buy_last_option_price_put'], is_call=False, is_long=True,
                delta=row.get('buy_delta_put'), iv=row.get('buy_iv_put'), theta=row.get('buy_theta_put'),
                oi=row.get('buy_open_interest_put'), volume=row.get('buy_day_volume_put'),
                expected_move=row.get('buy_expected_move_put')
            ),
            OptionLeg(
                strike=row['sell_strike_call'], premium=row['sell_last_option_price_call'], is_call=True, is_long=False,
                delta=row.get('sell_delta_call'), iv=row.get('sell_iv_call'), theta=row.get('sell_theta_call'),
                oi=row.get('sell_open_interest_call'), volume=row.get('sell_day_volume_call'),
                expected_move=row.get('sell_expected_move_call')
            ),
            OptionLeg(
                strike=row['buy_strike_call'], premium=row['buy_last_option_price_call'], is_call=True, is_long=True,
                delta=row.get('buy_delta_call'), iv=row.get('buy_iv_call'), theta=row.get('buy_theta_call'),
                oi=row.get('buy_open_interest_call'), volume=row.get('buy_day_volume_call'),
                expected_move=row.get('buy_expected_move_call')
            )
        ]
        
        metrics = StrategyMetrics(
            max_profit=row['max_profit'],
            max_loss=row['max_loss'] if 'max_loss' in row else row['bpr'],
            bpr=row['bpr'],
            expected_value=row['expected_value'],
            expected_value_managed=float(row.get('expected_value_managed', 0.0)),
            total_theta=float(row.get('total_theta', 0)),
            profit_to_bpr=float(row.get('profit_to_bpr', 0)),
            apdi=float(row.get('APDI', 0)),
            apdi_ev=float(row.get('APDI_EV', 0)),
            iv_correction_factor=float(row.get('iv_correction_factor', 1)),
            corrected_volatility=float(row.get('corrected_volatility', row.get('sell_iv', 0))),
            delta=float(row.get('delta', 0.0)),
            gamma=float(row.get('gamma', 0.0)),
            vega=float(row.get('vega', 0.0))
        )
        
        extra_info = {
            'iv_rank': row.get('iv_rank'),
            'iv_percentile': row.get('iv_percentile'),
            'company_sector': row.get('company_sector'),
            'company_industry': row.get('company_industry'),
            'analyst_mean_target': row.get('analyst_mean_target'),
            'close': row.get('close'),
            'optionstrat_url': row.get('optionstrat_url'),
            'Claude': row.get('Claude')
        }
        
        display_strategy_details(row['symbol'], row.get('Company', 'N/A'), legs, metrics, extra_info,
                                 context={'underlying_price': row.get('close', 100.0), 
                                          'volatility': row.get('sell_iv', 0.3), 
                                          'dte': int((pd.to_datetime(row['expiration_date_put']) - today).days), # Use put exp as proxy
                                          'take_profit': st.session_state.ic_take_profit,
                                          'stop_loss': st.session_state.ic_stop_loss,
                                          'dte_close': st.session_state.ic_dte_close})

    else:
        st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die Details der einzelnen Legs zu sehen.")
else:
    st.warning("No results found for the selected criteria.")
