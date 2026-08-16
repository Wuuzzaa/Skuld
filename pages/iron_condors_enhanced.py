import logging
import os
import streamlit as st
import concurrent.futures
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER, IV_CORRECTION_MODE, RISK_FREE_RATE
from pages.documentation_text.iron_condors_page_doc import get_iron_condor_documentation
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe, _create_claude_prompt_page_iron_condors
from src.iron_condor_calculation import calc_iron_condors, get_page_iron_condors_enhanced
from src.streamlit_helpers import render_date_filter
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.ui_strategy_display import display_strategy_details
from src.options_utils import OptionLeg, StrategyMetrics

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))

# --- Constants ---
DEFAULT_SHOW_MONTHLY = True
DEFAULT_SHOW_WEEKLY = False
DEFAULT_SHOW_DAILY = False
DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE = True
DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION = True
DEFAULT_DELTA_TARGET = 0.15
DEFAULT_MAX_RISK = 500        # dollars → width = floor(max_risk / 100)
DEFAULT_SPREAD_WIDTH_MIN = 1
DEFAULT_MIN_DAY_VOLUME = 20
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_IV_RANK = 0
DEFAULT_MIN_SELL_IV = 0.0     # lower default: ETFs/indices have lower IV
DEFAULT_MAX_SELL_IV = 0.9
DEFAULT_MIN_MAX_PROFIT = 50.0
DEFAULT_DELTA_CANDIDATES = 3
DEFAULT_STRATEGY = 'Iron Condor'
DEFAULT_DTE_MIN = 30
DEFAULT_DTE_MAX = 52

DTE_SLIDER_MAX = 90

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

# Dynamic title — set before session state so it updates on strategy change
_strategy_label = st.session_state.get('ice_strategy', DEFAULT_STRATEGY)
st.title(f"{'Iron Fly' if _strategy_label == 'Iron Fly' else 'Iron Condors'} Enhanced")

DEFAULTS = {
    'ice_show_monthly': DEFAULT_SHOW_MONTHLY,
    'ice_show_weekly': DEFAULT_SHOW_WEEKLY,
    'ice_show_daily': DEFAULT_SHOW_DAILY,
    'ice_show_only_positiv_expected_value': DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE,
    'ice_show_only_spreads_with_no_earnings': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION,
    'ice_delta_put': DEFAULT_DELTA_TARGET,
    'ice_delta_call': DEFAULT_DELTA_TARGET,
    'ice_max_risk': DEFAULT_MAX_RISK,
    'ice_spread_width_min': DEFAULT_SPREAD_WIDTH_MIN,
    'ice_min_sell_iv': DEFAULT_MIN_SELL_IV,
    'ice_max_sell_iv': DEFAULT_MAX_SELL_IV,
    'ice_min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'ice_iv_correction': IV_CORRECTION_MODE,
    'ice_risk_free_rate': RISK_FREE_RATE * 100,
    'ice_delta_candidates': DEFAULT_DELTA_CANDIDATES,
    'ice_asset_type': 'All',
    'ice_sectors': [],
    'ice_strategy': DEFAULT_STRATEGY,
    'ice_dte_min': DEFAULT_DTE_MIN,
    'ice_dte_max': DEFAULT_DTE_MAX,
}

init_session_state(DEFAULTS)


def _on_asset_type_change():
    if st.session_state.ice_asset_type in ('Indices', 'ETFs'):
        st.session_state.ice_min_sell_iv = 0.0
        st.session_state.ice_max_risk = 1000
        st.session_state.ice_delta_candidates = 5
        st.session_state.ice_show_only_spreads_with_no_earnings = False


def _on_strategy_change():
    if st.session_state.ice_strategy == 'Iron Fly':
        st.session_state.ice_delta_put = 0.50
        st.session_state.ice_delta_call = 0.50
        st.session_state.ice_max_risk = 500


def reset_to_defaults():
    ui_reset(DEFAULTS)


def clear_all_filters():
    st.session_state.ice_show_monthly = True
    st.session_state.ice_show_weekly = True
    st.session_state.ice_show_daily = True
    st.session_state.ice_show_only_positiv_expected_value = False
    st.session_state.ice_show_only_spreads_with_no_earnings = False
    st.session_state.ice_min_sell_iv = 0.0
    st.session_state.ice_max_sell_iv = 999.0
    st.session_state.ice_min_max_profit = 0.0


with st.expander("Documentation"):
    st.markdown(get_iron_condor_documentation())
    st.info(
        "**Enhanced** vs. Classic: delta_rank ≤ N, BETWEEN-Breite, Asset-Filter, Sektor-Filter, Min-IV 0. "
        "**Iron Fly**: beide Short-Strikes ATM (delta ~0.50), Flügel = Schutz."
    )

with st.expander("Configuration and Filters", expanded=True):
    # --- Strategy Toggle ---
    strat_col, btn_col1, btn_col2 = st.columns([2, 1, 1])
    with strat_col:
        st.radio(
            "Strategy",
            ['Iron Condor', 'Iron Fly'],
            key='ice_strategy',
            horizontal=True,
            on_change=_on_strategy_change,
        )
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, width="stretch")
    with btn_col2:
        st.button("Clear All Filters (Show All)", on_click=clear_all_filters, width="stretch")

    is_iron_fly = st.session_state.ice_strategy == 'Iron Fly'

    # --- Asset type + Sector ---
    asset_col, sector_col = st.columns([1, 2])
    with asset_col:
        st.radio(
            "Asset Type",
            ['All', 'Stocks', 'ETFs', 'Indices'],
            key='ice_asset_type',
            horizontal=True,
            on_change=_on_asset_type_change,
        )
    with sector_col:
        sectors_df = select_into_dataframe(
            sql_file_path=PATH_DATABASE_QUERY_FOLDER / 'get_sectors.sql',
            params={}
        )
        sector_list = sorted(sectors_df.iloc[:, 0].dropna().unique().tolist()) if not sectors_df.empty else []
        st.multiselect("Sectors (empty = all)", sector_list, key='ice_sectors')

    col1, col2, col3 = st.columns(3)

    with col1:
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path)

        filtered_dates_df = filter_by_expiration_type(
            dates_df,
            'expiration_date',
            st.session_state.ice_show_monthly,
            st.session_state.ice_show_weekly,
            st.session_state.ice_show_daily
        )

        dte_lo, dte_hi = st.slider(
            "DTE-Bereich (Tage bis Verfall)",
            min_value=0,
            max_value=DTE_SLIDER_MAX,
            value=(
                int(min(st.session_state.ice_dte_min, DTE_SLIDER_MAX)),
                int(min(st.session_state.ice_dte_max, DTE_SLIDER_MAX)),
            ),
            key="ice_dte_range",
        )
        st.session_state.ice_dte_min = dte_lo
        st.session_state.ice_dte_max = dte_hi

        range_dates_df = filtered_dates_df[
            (filtered_dates_df['days_to_expiration'] >= dte_lo) &
            (filtered_dates_df['days_to_expiration'] <= dte_hi)
        ]
        expiration_dates = range_dates_df['expiration_date'].tolist()

        if not expiration_dates:
            st.warning(f"Keine Verfallstermine im DTE-Bereich {dte_lo}–{dte_hi}. Slider anpassen.")
            st.stop()

        # Put und Call nutzen alle Termine im Range — Multi-Date Query
        expiration_date_put  = str(expiration_dates[0])
        expiration_date_call = str(expiration_dates[0])
        st.caption(f"{len(expiration_dates)} Verfallstermin(e) im Bereich {dte_lo}–{dte_hi} DTE")

    with col2:
        st.number_input("Put Delta Target", 0.0, 1.0, step=0.01, key="ice_delta_put",
                        disabled=is_iron_fly)
        st.number_input("Call Delta Target", 0.0, 1.0, step=0.01, key="ice_delta_call",
                        disabled=is_iron_fly)
        if is_iron_fly:
            st.info("Iron Fly: Short-Strikes ATM → delta ~0.50 (automatisch)")
        st.number_input("Delta Candidates", 1, 10, step=1, key="ice_delta_candidates",
                        help="Anzahl Sell-Kandidaten pro Symbol (delta_rank ≤ N). Höher = mehr Symbole.")

    with col3:
        st.number_input("Max Risk / Trade ($)", 100, 50000, step=100, key="ice_max_risk",
                        help="Max Risiko pro Seite in Dollar. Breite = floor(Wert/100) Punkte.")
        st.number_input("Min Spread Width (Punkte)", 1, 20, step=1, key="ice_spread_width_min",
                        help="Mindestbreite — verhindert 1-Punkte-Spreads.")

    # Spread width derived from max risk
    spread_width = max(1, int(st.session_state.ice_max_risk) // 100)
    spread_width_min = max(1, int(st.session_state.ice_spread_width_min))
    if spread_width < spread_width_min:
        spread_width = spread_width_min
    st.caption(f"Spread width: bis zu {spread_width} Punkte (mind. {spread_width_min})")

    col4, col5, col6 = st.columns(3)
    with col4:
        st.checkbox("Show Monthly", key="ice_show_monthly")
    with col5:
        st.checkbox("Show Weekly", key="ice_show_weekly")
    with col6:
        st.checkbox("Show Daily", key="ice_show_daily")

    col7, col8, col9 = st.columns(3)
    with col7:
        min_day_volume = st.number_input("Min Day Volume", 0, value=DEFAULT_MIN_DAY_VOLUME)
    with col8:
        min_open_interest = st.number_input("Min Open Interest", 0, value=DEFAULT_MIN_OPEN_INTEREST)
    with col9:
        min_iv_rank = st.number_input("Min IV Rank", 0, 100, value=DEFAULT_MIN_IV_RANK)

    col10, col11, col12 = st.columns(3)
    with col10:
        st.number_input("Min Sell IV", 0.0, step=0.05, format="%.2f", key="ice_min_sell_iv")
    with col11:
        st.number_input("Max Sell IV", 0.0, step=0.05, format="%.2f", key="ice_max_sell_iv")
    with col12:
        st.number_input("Min Max Profit", 0.0, step=1.0, format="%.2f", key="ice_min_max_profit")

    col13, col14 = st.columns(2)
    with col13:
        st.checkbox("Show only positive expected value", key="ice_show_only_positiv_expected_value")
    with col14:
        st.checkbox("Show only spreads with no earnings till expiration", key="ice_show_only_spreads_with_no_earnings")

    st.divider()
    col15, col16, col17 = st.columns(3)
    with col15:
        iv_corr_input = st.text_input("IV Correction (auto, 0.0-1.0)", value=str(st.session_state.ice_iv_correction), key="ice_iv_correction_input")
        if iv_corr_input.lower() == "auto":
            st.session_state.ice_iv_correction = "auto"
        else:
            try:
                st.session_state.ice_iv_correction = float(iv_corr_input)
            except ValueError:
                st.error("Invalid IV Correction. Use 'auto' or a number.")
                st.session_state.ice_iv_correction = 0.0
    with col16:
        st.number_input("Risk-Free Rate %", min_value=0.0, max_value=20.0, step=0.1, format="%.1f", key="ice_risk_free_rate")
    with col17:
        st.info("IV correction mode: 'auto' (Automatic), 0.0-1.0 (Manual reduction), 0.0 (No correction)")


@st.cache_data(ttl=300)
def _cached_select_query(date, query, params):
    return select_timetravel_into_dataframe(date=date, query=query, params=params)


@st.cache_data
def _cached_calc(put_df, call_df, iv_correction, risk_free_rate):
    return calc_iron_condors(put_df, call_df, iv_correction=iv_correction, risk_free_rate=risk_free_rate)


@st.cache_data
def _cached_get_page(ic_df_raw):
    return get_page_iron_condors_enhanced(ic_df_raw)


with st.spinner("Calculating Iron Condors Enhanced..."):
    common_params = {
        "min_open_interest": min_open_interest,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": 0,
        "delta_candidates": st.session_state.ice_delta_candidates,
        "spread_width": spread_width,
        "spread_width_min": spread_width_min,
    }

    multidate_sql_path = PATH_DATABASE_QUERY_FOLDER / 'iron_condors_enhanced_multidate_input.sql'
    with open(multidate_sql_path, 'r') as _f:
        _multidate_sql_raw = _f.read()

    exp_placeholders = ", ".join(f":d{i}" for i in range(len(expiration_dates)))
    date_params = {f"d{i}": d for i, d in enumerate(expiration_dates)}
    multidate_sql = _multidate_sql_raw.replace("__EXP_LIST__", exp_placeholders)

    put_params  = {**common_params, **date_params, "option_type": "put",  "delta_target": st.session_state.ice_delta_put}
    call_params = {**common_params, **date_params, "option_type": "call", "delta_target": st.session_state.ice_delta_call}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_put  = executor.submit(_cached_select_query, date=selected_date, query=multidate_sql, params=put_params)
        future_call = executor.submit(_cached_select_query, date=selected_date, query=multidate_sql, params=call_params)
        put_df  = future_put.result()
        call_df = future_call.result()

    ic_df_raw = _cached_calc(put_df, call_df, st.session_state.ice_iv_correction, st.session_state.ice_risk_free_rate / 100)
    ic_df = _cached_get_page(ic_df_raw)

# --- Asset type classification ---
if not ic_df.empty:
    def _classify(symbol, sector):
        if str(symbol).startswith('I:'):
            return 'index'
        if pd.isna(sector) or str(sector).strip() == '':
            return 'etf'
        return 'stock'

    ic_df['asset_type'] = ic_df.apply(
        lambda r: _classify(r['symbol'], r.get('company_sector')), axis=1
    )

    # Asset type filter
    asset_filter = st.session_state.ice_asset_type
    if asset_filter == 'Stocks':
        ic_df = ic_df[ic_df['asset_type'] == 'stock']
    elif asset_filter == 'ETFs':
        ic_df = ic_df[ic_df['asset_type'] == 'etf']
    elif asset_filter == 'Indices':
        ic_df = ic_df[ic_df['asset_type'] == 'index']

    # Sector filter (only meaningful for stocks)
    selected_sectors = st.session_state.ice_sectors
    if selected_sectors:
        ic_df = ic_df[ic_df['company_sector'].isin(selected_sectors)]

    # Best candidate per symbol+expiration: nächster Delta zum Ziel
    if not ic_df.empty:
        ic_df['_put_delta_dist'] = (ic_df['sell_delta_put'] - st.session_state.ice_delta_put).abs()
        ic_df['_call_delta_dist'] = (ic_df['sell_delta_call'] - st.session_state.ice_delta_call).abs()
        ic_df['_total_delta_dist'] = ic_df['_put_delta_dist'] + ic_df['_call_delta_dist']
        ic_df = ic_df.sort_values('_total_delta_dist').drop_duplicates(
            subset=['symbol', 'expiration_date_put'], keep='first'
        )
        ic_df = ic_df.drop(columns=['_put_delta_dist', '_call_delta_dist', '_total_delta_dist'])

if not ic_df.empty:
    # Min max profit
    ic_df = ic_df[ic_df['max_profit'] >= st.session_state.ice_min_max_profit]

    # Positive EV
    if st.session_state.ice_show_only_positiv_expected_value:
        ic_df = ic_df[ic_df['expected_value'] >= 0]

    # No earnings till expiration
    if st.session_state.ice_show_only_spreads_with_no_earnings:
        today = pd.Timestamp.now().normalize()
        ic_df['expiration_date_put'] = pd.to_datetime(ic_df['expiration_date_put']).dt.normalize()
        ic_df['expiration_date_call'] = pd.to_datetime(ic_df['expiration_date_call']).dt.normalize()
        ic_df['earnings_date'] = pd.to_datetime(ic_df['earnings_date']).dt.normalize()
        ic_df = ic_df[
            ~(
                (ic_df['earnings_date'] >= today) &
                (
                    (ic_df['earnings_date'] < ic_df['expiration_date_put']) |
                    (ic_df['earnings_date'] < ic_df['expiration_date_call'])
                )
            )
        ]

    # Sell IV filters
    if 'sell_iv' in ic_df.columns:
        ic_df = ic_df[ic_df['sell_iv'] >= st.session_state.ice_min_sell_iv]
        ic_df = ic_df[ic_df['sell_iv'] <= st.session_state.ice_max_sell_iv]

    ic_df.reset_index(drop=True, inplace=True)

    if not ic_df.empty:
        ic_df['earnings_date'] = pd.to_datetime(ic_df['earnings_date']).dt.strftime('%d.%m.%Y')

if not ic_df.empty:
    st.markdown(f"### {len(ic_df)} Results")

    column_config = {
        "asset_type": st.column_config.TextColumn(label="Type"),
        "days_to_expiration": st.column_config.NumberColumn(label="DTE", format="%d"),
        "optionstrat_url": st.column_config.LinkColumn(label="", help="OptionStrat", display_text="🎯"),
    }

    event = page_display_dataframe(
        ic_df,
        page='iron_condors',
        symbol_column='symbol',
        column_config=column_config,
        on_select="rerun",
        selection_mode="single-row"
    )

    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows and not ic_df.empty:
        selected_idx = selected_rows[0]
        row = ic_df.iloc[selected_idx]

        st.divider()

        # Verfallsdatum prominent zeigen — bei DTE-Range sind mehrere Termine gemischt
        _exp_put_disp  = pd.to_datetime(row['expiration_date_put']).strftime('%d.%m.%Y (%A)')
        _exp_call_disp = pd.to_datetime(row['expiration_date_call']).strftime('%d.%m.%Y (%A)')
        _dte_disp = int(row.get('days_to_expiration', 0))
        if row['expiration_date_put'] == row['expiration_date_call']:
            st.info(f"**{row['symbol']}**  ·  Verfall: **{_exp_put_disp}**  ·  **{_dte_disp} DTE**")
        else:
            st.info(f"**{row['symbol']}**  ·  Put: **{_exp_put_disp}**  ·  Call: **{_exp_call_disp}**  ·  **{_dte_disp} DTE**")

        legs = [
            OptionLeg(
                strike=row['sell_strike_put'], premium=row['sell_last_option_price_put'], is_call=False, is_long=False,
                delta=row['sell_delta_put'], iv=row['sell_iv_put'], theta=row['sell_theta_put'], oi=row['sell_open_interest_put'],
                volume=row.get('sell_day_volume_put'), expected_move=row.get('sell_expected_move_put'),
                last_updated_massive=row.get('sell_last_updated_put'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('sell_bs_price_put')
            ),
            OptionLeg(
                strike=row['buy_strike_put'], premium=row['buy_last_option_price_put'], is_call=False, is_long=True,
                delta=row['buy_delta_put'], iv=row['buy_iv_put'], theta=row['buy_theta_put'], oi=row['buy_open_interest_put'],
                volume=row.get('buy_day_volume_put'), expected_move=row.get('buy_expected_move_put'),
                last_updated_massive=row.get('buy_last_updated_put'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('buy_bs_price_put')
            ),
            OptionLeg(
                strike=row['sell_strike_call'], premium=row['sell_last_option_price_call'], is_call=True, is_long=False,
                delta=row['sell_delta_call'], iv=row['sell_iv_call'], theta=row['sell_theta_call'], oi=row['sell_open_interest_call'],
                volume=row.get('sell_day_volume_call'), expected_move=row.get('sell_expected_move_call'),
                last_updated_massive=row.get('sell_last_updated_call'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('sell_bs_price_call')
            ),
            OptionLeg(
                strike=row['buy_strike_call'], premium=row['buy_last_option_price_call'], is_call=True, is_long=True,
                delta=row['buy_delta_call'], iv=row['buy_iv_call'], theta=row['buy_theta_call'], oi=row['buy_open_interest_call'],
                volume=row.get('buy_day_volume_call'), expected_move=row.get('buy_expected_move_call'),
                last_updated_massive=row.get('buy_last_updated_call'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('buy_bs_price_call')
            ),
        ]

        metrics = StrategyMetrics(
            max_profit=row['max_profit'],
            max_loss=row['max_loss'] if 'max_loss' in row else row['bpr'],
            bpr=row['bpr'],
            expected_value=row['expected_value'],
            total_theta=row.get('total_theta', 0),
            profit_to_bpr=row.get('profit_to_bpr', 0),
            apdi=row.get('APDI', 0),
            apdi_ev=row.get('APDI_EV', 0),
            iv_correction_factor=row.get('iv_correction_factor', 1),
            corrected_volatility=row.get('corrected_volatility', row.get('sell_iv', 0))
        )

        extra_info = {
            'iv_rank': row.get('iv_rank'),
            'iv_percentile': row.get('iv_percentile'),
            'company_sector': row.get('company_sector'),
            'company_industry': row.get('company_industry'),
            'analyst_mean_target': row.get('analyst_mean_target'),
            'close': row.get('close'),
            'optionstrat_url': row.get('optionstrat_url'),
            'Claude': _create_claude_prompt_page_iron_condors(row)
        }

        display_strategy_details(row['symbol'], row.get('Company', 'N/A'), legs, metrics, extra_info)

    else:
        st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die Details der einzelnen Legs zu sehen.")
else:
    st.warning("No results found for the selected criteria.")
