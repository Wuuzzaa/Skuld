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
    'ic_min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'ic_iv_correction': IV_CORRECTION_MODE
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

@st.cache_data
def _cached_select_into_dataframe(sql_file_path, params):
    return select_into_dataframe(sql_file_path=sql_file_path, params=params)

@st.cache_data
def _cached_calc_iron_condors(put_df, call_df, iv_correction):
    return calc_iron_condors(put_df, call_df, iv_correction=iv_correction)

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
    put_df = _cached_select_into_dataframe(sql_file_path=sql_query_path, params=put_params)
    
    # Get Call Spreads
    call_params = {**common_params, "expiration_date": expiration_date_call, "option_type": "call", "delta_target": st.session_state.ic_delta_call, "spread_width": st.session_state.ic_width_call}
    call_df = _cached_select_into_dataframe(sql_file_path=sql_query_path, params=call_params)
    
    ic_df_raw = _cached_calc_iron_condors(put_df, call_df, st.session_state.ic_iv_correction)
    ic_df = get_page_iron_condors(ic_df_raw)

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

    # Format earnings date for display
    if not ic_df.empty:
        ic_df['earnings_date'] = pd.to_datetime(ic_df['earnings_date']).dt.strftime('%d.%m.%Y')
        ic_df.reset_index(drop=True, inplace=True)

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
        st.subheader(f"Details für {row['symbol']} Iron Condor")

        # Create detailed table for legs
        legs_data = [
            {
                "Leg": "Short Put",
                "Strike": row['sell_strike_put'],
                "Price": row['sell_last_option_price_put'],
                "Delta": row['sell_delta_put'],
                "IV": row['sell_iv_put'],
                "Theta": row['sell_theta_put'],
                "OI": row['sell_open_interest_put'],
                "Volume": row.get('sell_day_volume_put'),
                "Exp Move": row.get('sell_expected_move_put')
            },
            {
                "Leg": "Long Put",
                "Strike": row['buy_strike_put'],
                "Price": row['buy_last_option_price_put'],
                "Delta": row['buy_delta_put'],
                "IV": row['buy_iv_put'],
                "Theta": row['buy_theta_put'],
                "OI": row['buy_open_interest_put'],
                "Volume": row.get('buy_day_volume_put'),
                "Exp Move": row.get('buy_expected_move_put')
            },
            {
                "Leg": "Short Call",
                "Strike": row['sell_strike_call'],
                "Price": row['sell_last_option_price_call'],
                "Delta": row['sell_delta_call'],
                "IV": row['sell_iv_call'],
                "Theta": row['sell_theta_call'],
                "OI": row['sell_open_interest_call'],
                "Volume": row.get('sell_day_volume_call'),
                "Exp Move": row.get('sell_expected_move_call')
            },
            {
                "Leg": "Long Call",
                "Strike": row['buy_strike_call'],
                "Price": row['buy_last_option_price_call'],
                "Delta": row['buy_delta_call'],
                "IV": row['buy_iv_call'],
                "Theta": row['buy_theta_call'],
                "OI": row['buy_open_interest_call'],
                "Volume": row.get('buy_day_volume_call'),
                "Exp Move": row.get('buy_expected_move_call')
            }
        ]
        
        logger.debug(f"Legs data for {row['symbol']}: {legs_data}")
        
        details_df = pd.DataFrame(legs_data)
        st.table(details_df)
        
        # Additional Info
        st.markdown("#### Kennzahlen & Unternehmensinfos")

        st.write(f"**Unternehmen:** {row.get('Company', 'N/A')}")

        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        with col_info1:
            max_profit = row.get('max_profit')
            st.metric("Max Profit", f"${max_profit:.2f}" if pd.notnull(max_profit) else "N/A")
            bpr = row.get('bpr')
            st.metric("BPR", f"${bpr:.2f}" if pd.notnull(bpr) else "N/A")
        with col_info2:
            expected_value = row.get('expected_value')
            st.metric("Expected Value", f"${expected_value:.2f}" if pd.notnull(expected_value) else "N/A")
            apdi = row.get('APDI')
            st.metric("APDI", f"{apdi:.2f}%" if pd.notnull(apdi) else "N/A")
        with col_info3:
            iv_rank = row.get('iv_rank')
            st.metric("IV Rank", f"{iv_rank:.1f}" if pd.notnull(iv_rank) else "N/A")
            
            iv_percentile = row.get('iv_percentile')
            st.metric("IV Percentile", f"{iv_percentile:.1f}" if pd.notnull(iv_percentile) else "N/A")
        with col_info4:
            st.metric("Sell IV (Avg)", f"{row.get('sell_iv', 0)*100:.1f}%")
            st.metric("Theta", f"{row.get('total_theta', 0):.4f}")

        iv_corr_display = str(st.session_state.ic_iv_correction)
        if st.session_state.ic_iv_correction == "auto" and "iv_correction_factor" in row:
            iv_corr_display = f"auto ({row['iv_correction_factor']*100:.1f}%)"
        st.write(f"**IV Correction Setting:** {iv_corr_display}")
        st.write(f"**Sektor:** {row.get('company_sector', 'N/A')} | **Branche:** {row.get('company_industry', 'N/A')}")

        if 'analyst_mean_target' in row and pd.notnull(row['analyst_mean_target']):
            st.write(f"**Analyst Kursziel:** ${row['analyst_mean_target']:.2f} (Aktuell: ${row.get('close', 0):.2f})")

        # External Links
        st.markdown("#### Links")
        link_col1, link_col2, link_col3, link_col4 = st.columns(4)
        with link_col1:
            st.link_button("TradingView", f"https://www.tradingview.com/symbols/{row['symbol']}/", use_container_width=True)
            st.link_button("Chart", f"https://www.tradingview.com/chart/?symbol={row['symbol']}", use_container_width=True)
        with link_col2:
            st.link_button("Finviz", f"https://finviz.com/quote.ashx?t={row['symbol']}", use_container_width=True)
            if 'optionstrat_url' in row and row['optionstrat_url']:
                st.link_button("OptionStrat", row['optionstrat_url'], use_container_width=True)
        with link_col3:
            st.link_button("Seeking Alpha", f"https://seekingalpha.com/symbol/{row['symbol']}", use_container_width=True)
            if 'Claude' in row and row['Claude']:
                st.link_button("Claude AI Analysis", row['Claude'], use_container_width=True)
        with link_col4:
            st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{row['symbol']}", use_container_width=True)

    else:
        st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die Details der einzelnen Legs zu sehen.")
else:
    st.warning("No results found for the selected criteria.")
