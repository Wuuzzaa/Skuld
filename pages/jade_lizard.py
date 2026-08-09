import logging
import os
import streamlit as st
import concurrent.futures
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER, IV_CORRECTION_MODE, RISK_FREE_RATE
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.iron_condor_calculation import calc_iron_condors, get_page_iron_condors_enhanced, calc_jade_lizards, get_page_jade_lizards
from src.streamlit_helpers import render_date_filter
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))

DEFAULT_SHOW_MONTHLY = True
DEFAULT_SHOW_WEEKLY = False
DEFAULT_SHOW_DAILY = False
DEFAULT_DELTA_PUT = 0.16       # OTM short put
DEFAULT_DELTA_CALL = 0.16      # OTM short call (sell side of call spread)
DEFAULT_MAX_RISK = 300          # call spread width = floor(max_risk/100)
DEFAULT_SPREAD_WIDTH_MIN = 1
DEFAULT_MIN_DAY_VOLUME = 20
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_IV_RANK = 0
DEFAULT_MIN_SELL_IV = 0.0
DEFAULT_MAX_SELL_IV = 0.9
DEFAULT_MIN_CREDIT = 50.0
DEFAULT_DELTA_CANDIDATES = 3
DEFAULT_SHOW_ONLY_NO_EARNINGS = True
DTE_SLIDER_MAX = 90

DEFAULTS = {
    'jl_show_monthly': DEFAULT_SHOW_MONTHLY,
    'jl_show_weekly': DEFAULT_SHOW_WEEKLY,
    'jl_show_daily': DEFAULT_SHOW_DAILY,
    'jl_delta_put': DEFAULT_DELTA_PUT,
    'jl_delta_call': DEFAULT_DELTA_CALL,
    'jl_max_risk': DEFAULT_MAX_RISK,
    'jl_spread_width_min': DEFAULT_SPREAD_WIDTH_MIN,
    'jl_min_sell_iv': DEFAULT_MIN_SELL_IV,
    'jl_max_sell_iv': DEFAULT_MAX_SELL_IV,
    'jl_min_credit': DEFAULT_MIN_CREDIT,
    'jl_delta_candidates': DEFAULT_DELTA_CANDIDATES,
    'jl_asset_type': 'All',
    'jl_sectors': [],
    'jl_show_only_no_earnings': DEFAULT_SHOW_ONLY_NO_EARNINGS,
    'jl_only_no_upside_risk': True,
}

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

st.title("Jade Lizard")
st.caption(
    "Short OTM Put + Short OTM Call Spread. "
    "Tastylive-Regel: Total Credit > Call Spread Width → kein Upside-Risiko."
)

init_session_state(DEFAULTS)


def _on_asset_type_change():
    if st.session_state.jl_asset_type in ('Indices', 'ETFs'):
        st.session_state.jl_min_sell_iv = 0.0
        st.session_state.jl_delta_candidates = 5
        st.session_state.jl_show_only_no_earnings = False


def reset_to_defaults():
    ui_reset(DEFAULTS)


def clear_all_filters():
    st.session_state.jl_show_monthly = True
    st.session_state.jl_show_weekly = True
    st.session_state.jl_show_daily = True
    st.session_state.jl_min_sell_iv = 0.0
    st.session_state.jl_max_sell_iv = 999.0
    st.session_state.jl_min_credit = 0.0
    st.session_state.jl_show_only_no_earnings = False
    st.session_state.jl_only_no_upside_risk = False


with st.expander("Configuration and Filters", expanded=True):
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, width="stretch")
    with btn_col2:
        st.button("Clear All Filters", on_click=clear_all_filters, width="stretch")

    asset_col, sector_col = st.columns([1, 2])
    with asset_col:
        st.radio("Asset Type", ['All', 'Stocks', 'ETFs', 'Indices'],
                 key='jl_asset_type', horizontal=True, on_change=_on_asset_type_change)
    with sector_col:
        sectors_df = select_into_dataframe(
            sql_file_path=PATH_DATABASE_QUERY_FOLDER / 'get_sectors.sql', params={})
        sector_list = sorted(sectors_df.iloc[:, 0].dropna().unique().tolist()) if not sectors_df.empty else []
        st.multiselect("Sectors (empty = all)", sector_list, key='jl_sectors')

    col1, col2, col3 = st.columns(3)
    with col1:
        dates_df = select_timetravel_into_dataframe(
            date=selected_date,
            sql_file_path=PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql')
        filtered_dates = filter_by_expiration_type(
            dates_df, 'expiration_date',
            st.session_state.jl_show_monthly,
            st.session_state.jl_show_weekly,
            st.session_state.jl_show_daily)
        slider_dates = filtered_dates[filtered_dates['days_to_expiration'].astype(int) <= DTE_SLIDER_MAX]
        if slider_dates.empty:
            slider_dates = filtered_dates

        dte_labels = [
            f"{int(r['days_to_expiration'])} DTE - "
            f"{pd.to_datetime(r['expiration_date']).strftime('%A')}  "
            f"{r['expiration_date']} - {get_expiration_type(r['expiration_date'])}"
            for _, r in slider_dates.iterrows()
        ]
        if not dte_labels:
            st.warning("No expiration dates match the selected filters.")
            st.stop()

        exp_sel = st.selectbox("Expiration", dte_labels, index=min(1, len(dte_labels) - 1))
        expiration_date = str(slider_dates.iloc[dte_labels.index(exp_sel)]['expiration_date'])

    with col2:
        st.number_input("Put Delta Target (Short Put)", 0.0, 1.0, step=0.01, key="jl_delta_put")
        st.number_input("Call Delta Target (Short Call)", 0.0, 1.0, step=0.01, key="jl_delta_call")
        st.number_input("Delta Candidates", 1, 10, step=1, key="jl_delta_candidates")

    with col3:
        st.number_input("Max Risk Call Spread ($)", 100, 10000, step=100, key="jl_max_risk",
                        help="Call Spread Breite = floor(Wert/100) Punkte")
        st.number_input("Min Spread Width (Punkte)", 1, 20, step=1, key="jl_spread_width_min")

    spread_width = max(1, int(st.session_state.jl_max_risk) // 100)
    spread_width_min = max(1, int(st.session_state.jl_spread_width_min))
    if spread_width < spread_width_min:
        spread_width = spread_width_min
    st.caption(f"Call Spread width: bis zu {spread_width} Punkte (mind. {spread_width_min})")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.checkbox("Show Monthly", key="jl_show_monthly")
    with col5:
        st.checkbox("Show Weekly", key="jl_show_weekly")
    with col6:
        st.checkbox("Show Daily", key="jl_show_daily")

    col7, col8, col9 = st.columns(3)
    with col7:
        min_day_volume = st.number_input("Min Day Volume", 0, value=DEFAULT_MIN_DAY_VOLUME)
    with col8:
        min_open_interest = st.number_input("Min Open Interest", 0, value=DEFAULT_MIN_OPEN_INTEREST)
    with col9:
        min_iv_rank = st.number_input("Min IV Rank", 0, 100, value=DEFAULT_MIN_IV_RANK)

    col10, col11, col12 = st.columns(3)
    with col10:
        st.number_input("Min Total Credit ($)", 0.0, step=10.0, key="jl_min_credit")
    with col11:
        st.number_input("Min Sell IV", 0.0, step=0.05, format="%.2f", key="jl_min_sell_iv")
    with col12:
        st.number_input("Max Sell IV", 0.0, step=0.05, format="%.2f", key="jl_max_sell_iv")

    col13, col14 = st.columns(2)
    with col13:
        st.checkbox("Only trades with no upside risk (Credit > Spread Width)", key="jl_only_no_upside_risk")
    with col14:
        st.checkbox("No earnings till expiration", key="jl_show_only_no_earnings")


@st.cache_data(ttl=300)
def _cached_select(date, sql_file_path, params):
    return select_timetravel_into_dataframe(date=date, sql_file_path=sql_file_path, params=params)


@st.cache_data
def _cached_calc(put_df, call_spread_df):
    return calc_jade_lizards(put_df, call_spread_df)


@st.cache_data
def _cached_page(df):
    return get_page_jade_lizards(df)


with st.spinner("Calculating Jade Lizards..."):
    common_params = {
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": 0,
        "delta_candidates": st.session_state.jl_delta_candidates,
        "spread_width": spread_width,
        "spread_width_min": spread_width_min,
    }
    # Put: plain legs from short_strangle_input (no spread needed)
    put_sql  = PATH_DATABASE_QUERY_FOLDER / 'short_strangle_input.sql'
    # Call spread: reuse iron_condors_enhanced_input (already has BETWEEN-width logic)
    call_sql = PATH_DATABASE_QUERY_FOLDER / 'iron_condors_enhanced_input.sql'

    put_params = {
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": 0,
        "delta_candidates": st.session_state.jl_delta_candidates,
        "expiration_date": expiration_date,
        "option_type": "put",
        "delta_target": st.session_state.jl_delta_put,
    }
    call_params = {**common_params,
                   "expiration_date": expiration_date,
                   "option_type": "call",
                   "delta_target": st.session_state.jl_delta_call}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_put  = executor.submit(_cached_select, date=selected_date, sql_file_path=put_sql,  params=put_params)
        f_call = executor.submit(_cached_select, date=selected_date, sql_file_path=call_sql, params=call_params)
        put_df       = f_put.result()
        call_spread_df = f_call.result()

    # call_spread_df columns from iron_condors_enhanced_input use sell_/buy_ prefix
    raw = _cached_calc(put_df, call_spread_df)
    df  = _cached_page(raw)

# --- Asset classification + filters ---
if not df.empty:
    def _classify(symbol, sector):
        if str(symbol).startswith('I:'):
            return 'index'
        if pd.isna(sector) or str(sector).strip() == '':
            return 'etf'
        return 'stock'

    df['asset_type'] = df.apply(lambda r: _classify(r['symbol'], r.get('company_sector')), axis=1)

    asset_filter = st.session_state.jl_asset_type
    if asset_filter == 'Stocks':
        df = df[df['asset_type'] == 'stock']
    elif asset_filter == 'ETFs':
        df = df[df['asset_type'] == 'etf']
    elif asset_filter == 'Indices':
        df = df[df['asset_type'] == 'index']

    if st.session_state.jl_sectors:
        df = df[df['company_sector'].isin(st.session_state.jl_sectors)]

    # Best candidate per symbol
    if not df.empty:
        df['_delta_dist'] = (df['delta_put'] - st.session_state.jl_delta_put).abs()
        df = df.sort_values('_delta_dist').drop_duplicates(subset=['symbol'], keep='first')
        df = df.drop(columns=['_delta_dist'])

if not df.empty:
    df = df[df['total_credit_dollar'] >= st.session_state.jl_min_credit]

    if 'sell_iv' in df.columns:
        df = df[df['sell_iv'] >= st.session_state.jl_min_sell_iv]
        df = df[df['sell_iv'] <= st.session_state.jl_max_sell_iv]

    if st.session_state.jl_only_no_upside_risk and 'no_upside_risk' in df.columns:
        df = df[df['no_upside_risk'] == True]

    if st.session_state.jl_show_only_no_earnings:
        today = pd.Timestamp.now().normalize()
        df['expiration_date_put']  = pd.to_datetime(df['expiration_date_put']).dt.normalize()
        df['expiration_date_call'] = pd.to_datetime(df['expiration_date_call']).dt.normalize()
        df['earnings_date']        = pd.to_datetime(df['earnings_date']).dt.normalize()
        df = df[~(
            (df['earnings_date'] >= today) &
            ((df['earnings_date'] < df['expiration_date_put']) |
             (df['earnings_date'] < df['expiration_date_call']))
        )]

    df.reset_index(drop=True, inplace=True)
    if not df.empty:
        df['earnings_date'] = pd.to_datetime(df['earnings_date']).dt.strftime('%d.%m.%Y')

if not df.empty:
    st.markdown(f"### {len(df)} Results")

    no_risk_count = int(df['no_upside_risk'].sum()) if 'no_upside_risk' in df.columns else 0
    st.info(
        f"✅ **{no_risk_count}** Trades ohne Upside-Risiko (Credit > Spread-Breite). "
        "Put-Seite bleibt undefined risk nach unten."
    )

    column_config = {
        "asset_type": st.column_config.TextColumn(label="Type"),
        "no_upside_risk": st.column_config.CheckboxColumn(label="No ↑ Risk"),
        "total_credit_dollar": st.column_config.NumberColumn(label="Credit $", format="$%.0f"),
        "max_loss_call_side": st.column_config.NumberColumn(label="Call MaxLoss $", format="$%.0f"),
        "optionstrat_url": st.column_config.LinkColumn(label="", help="OptionStrat", display_text="🎯"),
    }
    page_display_dataframe(df, page='spreads', symbol_column='symbol',
                           column_config=column_config, on_select="rerun", selection_mode="single-row")
else:
    st.warning("No results found for the selected criteria.")
