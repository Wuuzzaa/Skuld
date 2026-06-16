import logging
import os
from datetime import datetime, date

import streamlit as st
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER, IV_CORRECTION_MODE, RISK_FREE_RATE
from pages.documentation_text.spreads_page_doc import get_spreads_documentation
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe, _create_claude_prompt_page_spreads
from src.spreads_calculation import get_page_spreads
from src.streamlit_helpers import render_date_filter
from src.utils.option_utils import get_expiration_type
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.ui_strategy_display import display_strategy_details
from src.options_utils import OptionLeg, StrategyMetrics
import plotly.graph_objects as go

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
DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_WARNING = True
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
DEFAULT_STRATEGY_TYPE = "credit"

# Page header
st.title("Spreads")

# Default values mapping for UI utils
DEFAULTS = {
    'show_monthly': DEFAULT_SHOW_MONTHLY,
    'show_weekly': DEFAULT_SHOW_WEEKLY,
    'show_daily': DEFAULT_SHOW_DAILY,
    'show_only_positiv_expected_value': DEFAULT_SHOW_ONLY_POSITIV_EXPECTED_VALUE,
    'show_only_spreads_with_no_earnings_till_expiration': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_TILL_EXPIRATION,
    'show_only_spreads_with_no_earnings_warning': DEFAULT_SHOW_ONLY_SPREADS_WITH_NO_EARNINGS_WARNING,
    'delta_target': DEFAULT_DELTA_TARGET,
    'spread_width': DEFAULT_SPREAD_WIDTH,
    'option_type': DEFAULT_OPTION_TYPE,
    'min_day_volume': DEFAULT_MIN_DAY_VOLUME,
    'min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'min_sell_iv': DEFAULT_MIN_SELL_IV,
    'max_sell_iv': DEFAULT_MAX_SELL_IV,
    'min_max_profit': DEFAULT_MIN_MAX_PROFIT,
    'min_iv_rank': DEFAULT_MIN_IV_RANK,
    'min_iv_percentile': DEFAULT_MIN_IV_PERCENTILE,
    'strategy_type': DEFAULT_STRATEGY_TYPE,
    'iv_correction': IV_CORRECTION_MODE,
    'risk_free_rate': RISK_FREE_RATE * 100  # stored as percentage for UI (e.g. 3.0 = 3%)
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
    st.session_state.show_only_spreads_with_no_earnings_warning = False
    st.session_state.min_day_volume = 0
    st.session_state.min_open_interest = 0
    st.session_state.min_sell_iv = 0.0
    st.session_state.max_sell_iv = 999.0
    st.session_state.min_max_profit = 0.0
    st.session_state.min_iv_rank = 0
    st.session_state.min_iv_percentile = 0

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

# Filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    # Action buttons
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        st.button("Reset to Defaults", on_click=reset_to_defaults, width="stretch")
    with btn_col2:
        st.button("Clear All Filters (Show All)", on_click=clear_all_filters, width="stretch")

    # First row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path)

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
        selected_label = st.selectbox("Expiration Date", dte_labels, index=min(1, len(dte_labels)-1))

        # Extract selected expiration date from DTE label
        selected_index = dte_labels.index(selected_label)
        expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']
        logging.debug(f"Extracted selected expiration date: {expiration_date}")

    with col2:
        # Suggest different delta for debit
        default_delta = 0.6 if st.session_state.strategy_type == "debit" else 0.2
        delta_target = st.number_input(
            "Delta Target",
            min_value=0.0,
            max_value=1.0,
            value=default_delta,
            step=0.01,
            key="delta_target_input"
        )
        # We need to handle the session state correctly if it was already set
        st.session_state.delta_target = delta_target

    with col3:
        spread_width = st.number_input(
            "Spread Width",
            min_value=1,
            max_value=20,
            step=1,
            key="spread_width"
        )

    with col4:
        strategy_type = st.selectbox("Strategy Type", ["credit", "debit"], key="strategy_type")

    # Second row
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        option_type = st.selectbox("Option Type", ["put", "call"], key="option_type")

    with col6:
        st.checkbox("Show Monthly", key="show_monthly")

    with col7:
        st.checkbox("Show Weekly", key="show_weekly")

    with col8:
        st.checkbox("Show Daily", key="show_daily")

    # Third row
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        st.checkbox(
            "Show only positive expected value",
            key="show_only_positiv_expected_value"
        )
    
    with col10:
        st.checkbox(
            "Earnings Warning Filter",
            key="show_only_spreads_with_no_earnings_warning",
            help="Filters out spreads with an earnings warning (earnings shortly before expiration)"
        )

    with col11:
        min_day_volume = st.number_input(
            "Min dayvolume",
            min_value=0,
            step=1,
            key="min_day_volume"
        )

    with col12:
        min_open_interest = st.number_input(
            "Min Open Interest",
            min_value=0,
            step=100,
            key="min_open_interest"
        )

    with col12:
        min_sell_iv = st.number_input(
            "Min sell iv",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="min_sell_iv"
        )

    # Fourth row
    col13, col14, col15, col16 = st.columns(4)

    with col13:
        max_sell_iv = st.number_input(
            "Max sell iv",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="max_sell_iv"
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

    st.divider()
    col17, col18, col19 = st.columns(3)
    with col17:
        iv_corr_input = st.text_input("IV Correction (auto, 0.0-1.0)", value=str(st.session_state.iv_correction), key="iv_correction_input")
        if iv_corr_input.lower() == "auto":
            st.session_state.iv_correction = "auto"
        else:
            try:
                st.session_state.iv_correction = float(iv_corr_input)
            except ValueError:
                st.error("Invalid IV Correction. Use 'auto' or a number.")
                st.session_state.iv_correction = 0.0
    with col18:
        st.number_input("Risk-Free Rate %", min_value=0.0, max_value=20.0, step=0.1, format="%.1f", key="risk_free_rate")
    with col19:
        st.info("IV correction mode: 'auto' (Automatic), 0.0-1.0 (Manual reduction), 0.0 (No correction)")

@st.cache_data(ttl=300)  # 5 Minuten
def _cached_select_into_dataframe(date, sql_file_path, params):
    return select_timetravel_into_dataframe(date=date, sql_file_path=sql_file_path, params=params)


@st.cache_data(ttl=300)  # 5 Minuten
def _cached_get_page_spreads(df, strategy_type, iv_correction, risk_free_rate):
    return get_page_spreads(df, strategy_type=strategy_type, iv_correction=iv_correction, risk_free_rate=risk_free_rate)


def parse_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


@st.cache_data(ttl=300)
def get_option_data_at_date(option_osi, selected_date):
    sql = """
        SELECT
            option_osi,
            symbol,
            contract_type,
            expiration_date,
            strike_price,
            premium_option_price,
            shares_per_contract,
            LIVE_STOCK_PRICE AS close
        FROM "OptionDataMerged"
        WHERE option_osi = :option_osi
    """
    return select_timetravel_into_dataframe(
        date=selected_date,
        query=sql,
        params={"option_osi": option_osi}
    )

@st.cache_data(ttl=300)
def get_option_date_range(option_osi, from_date, to_date):
    sql = """
        SELECT
            date,
            option_osi,
            symbol,
            contract_type,
            expiration_date,
            strike_price,
            day_close AS premium_option_price,
            shares_per_contract
        FROM "OptionDataMassiveHistory"
        WHERE option_osi = :option_osi
        AND date BETWEEN :from_date AND :to_date
    """
    return select_into_dataframe(
        query=sql,
        params={"option_osi": option_osi, "from_date": from_date, "to_date": to_date}
    )

@st.cache_data(ttl=300)
def get_stock_date_range(symbol, from_date, to_date):
    sql = """
        SELECT
            date,
            symbol,
            close
        FROM "StockPricesYahooHistory"
        WHERE symbol = :symbol
        AND date BETWEEN :from_date AND :to_date
    """
    return select_into_dataframe(
        query=sql,
        params={"symbol": symbol, "from_date": from_date, "to_date": to_date}
    )

# Calculate the spread values with a loading indicator
with st.spinner("Calculating spreads..."):
    params = {
        "expiration_date": expiration_date,
        "option_type": option_type,
        "delta_target": st.session_state.delta_target,
        "min_open_interest": min_open_interest,
        "spread_width": spread_width,
        "min_day_volume": min_day_volume,
        "min_iv_rank": min_iv_rank,
        "min_iv_percentile": min_iv_percentile,
        "strategy_type": strategy_type
    }

    logging.debug(f"Params for database query: {params}")

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
    df = _cached_select_into_dataframe(date=selected_date, sql_file_path=sql_file_path, params=params)
    logging.debug(f"Input data head: {df.head()}")

    spreads_df = _cached_get_page_spreads(df, strategy_type=strategy_type, iv_correction=st.session_state.iv_correction, risk_free_rate=st.session_state.risk_free_rate / 100)
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
expiration_date_ts = pd.Timestamp(expiration_date).normalize()

if st.session_state.show_only_spreads_with_no_earnings_till_expiration:
    filtered_df = filtered_df[
        ~(
                (pd.to_datetime(filtered_df['earnings_date']).dt.normalize() >= today) &
                (pd.to_datetime(filtered_df['earnings_date']).dt.normalize() < expiration_date_ts)
        )
    ]

# Earnings Warning Filter
if st.session_state.show_only_spreads_with_no_earnings_warning:
    if 'earnings_warning' in filtered_df.columns:
        filtered_df = filtered_df[
            (filtered_df['earnings_warning'] == '') | (filtered_df['earnings_warning'].isna())
        ]

# Reset index to ensure the zebra style works on the dataframe
filtered_df.reset_index(drop=True, inplace=True)

# Min sell IV
filtered_df = filtered_df[filtered_df['sell_iv'] >= min_sell_iv]

# Max sell IV
filtered_df = filtered_df[filtered_df['sell_iv'] <= max_sell_iv]

# Re-reset index after all filters are applied
filtered_df.reset_index(drop=True, inplace=True)

# Format 'earnings_date' for display (do this AFTER all calculations and filtering)
filtered_df['earnings_date'] = pd.to_datetime(filtered_df['earnings_date']).dt.strftime('%d.%m.%Y')

# Pre-format columns that we want to show in details but not in the main table
# This ensures they are available in 'row' even after page_display_dataframe might have dropped them from display
# Actually page_display_dataframe creates a copy for display, so filtered_df remains intact.

st.markdown(f"### {len(filtered_df)} Results")

# Export All button - downloads all filtered spreads with full details as CSV
if not filtered_df.empty:
    export_columns = [
        'symbol', 'Company', 'close', 'option_type',
        'sell_strike', 'sell_last_option_price', 'sell_delta', 'sell_iv', 'sell_theta',
        'sell_open_interest', 'sell_day_volume', 'sell_expected_move',
        'buy_strike', 'buy_last_option_price', 'buy_delta', 'buy_iv', 'buy_theta',
        'buy_open_interest', 'buy_day_volume', 'buy_expected_move',
        'spread_width', 'max_profit', 'bpr', 'profit_to_bpr',
        'expected_value', 'APDI', 'APDI_EV',
        'iv_rank', 'iv_percentile', 'iv_correction_factor',
        'spread_theta', '%_otm', 'days_to_expiration',
        'earnings_date', 'earnings_warning',
        'company_sector', 'company_industry', 'analyst_mean_target',
    ]
    # Only include columns that actually exist in the dataframe
    available_cols = [c for c in export_columns if c in filtered_df.columns]
    export_df = filtered_df[available_cols]
    csv_data = export_df.to_csv(index=False)
    st.download_button(
        label=f"⬇️ Export All ({len(filtered_df)} trades) as CSV",
        data=csv_data,
        file_name=f"spreads_{option_type}_{spread_width}w_{expiration_date}.csv",
        mime="text/csv",
    )

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
if not filtered_df.empty:
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        row = filtered_df.iloc[selected_idx]

        st.divider()
        
        is_credit = strategy_type == "credit"
        
        legs = [
            OptionLeg(
                strike=row['sell_strike'], premium=row['sell_last_option_price'],
                is_call=row['option_type'] == 'call', is_long=not is_credit,
                delta=row.get('sell_delta'), iv=row.get('sell_iv'),
                theta=row.get('sell_theta'), oi=row.get('sell_open_interest'),
                volume=row.get('sell_day_volume'), expected_move=row.get('sell_expected_move'),
                last_updated_massive=row.get('sell_last_updated'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('sell_bs_price')
            ),
            OptionLeg(
                strike=row['buy_strike'], premium=row['buy_last_option_price'],
                is_call=row['option_type'] == 'call', is_long=is_credit,
                delta=row.get('buy_delta'), iv=row.get('buy_iv'),
                theta=row.get('buy_theta'), oi=row.get('buy_open_interest'),
                volume=row.get('buy_day_volume'), expected_move=row.get('buy_expected_move'),
                last_updated_massive=row.get('buy_last_updated'),
                last_updated_option_data=row.get('last_updated_option_data'),
                last_updated_stock_data=row.get('last_updated_stock_data'),
                bs_price=row.get('buy_bs_price')
            )
        ]

        metrics = StrategyMetrics(
            max_profit=row['max_profit'],
            max_loss=row['max_loss'] if 'max_loss' in row else row['bpr'],
            bpr=row['bpr'],
            expected_value=row['expected_value'],
            total_theta=row.get('spread_theta', 0),
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
            'Claude': _create_claude_prompt_page_spreads(row)
        }

        display_strategy_details(row['symbol'], row.get('Company', 'N/A'), legs, metrics, extra_info)

        # Time Travel Simulation for the selected comparison date
        st.divider()
        st.subheader("📈 Simulierter Exit zum Vergleichsdatum")
        compare_date = render_date_filter(
            date_query=f'select date from (select date from "DatesHistory" union select current_date) as sub WHERE date <= \'{row['expiration_date']}\' ORDER BY date DESC',
            date_label="Vergleichsdatum für Verkauf:",
            date_session_key="spread_compare_date",
            date_list_session_key="spread_date_list_compare" + str(row['expiration_date'].strftime('%Y%m%d')),
            date_index=0,
        )
        
        if parse_date(compare_date) == parse_date(selected_date):
            st.info("Wähle ein anderes Vergleichsdatum als das Einstiegdatum.")
        else:
            sell_exit_df = get_option_data_at_date(row['sell_option_osi'], compare_date)
            buy_exit_df = get_option_data_at_date(row['buy_option_osi'], compare_date)
            sell_option_date_range_df = get_option_date_range(row['sell_option_osi'], selected_date, compare_date)
            buy_option_date_range_df = get_option_date_range(row['buy_option_osi'], selected_date, compare_date)
            stock_date_range_df = get_stock_date_range(row['symbol'], selected_date, compare_date)
            logger.info(f"Option data points {len(sell_option_date_range_df)}")
            logger.info(f"Stock data points {len(stock_date_range_df)}")


            if sell_exit_df is None or buy_exit_df is None or sell_exit_df.empty or buy_exit_df.empty:
                st.warning("Die Option konnte für das Vergleichsdatum nicht geladen werden.")
            else:
                # 1. Daten sauber auslesen
                exit_sell_price = float(sell_exit_df.iloc[0]['premium_option_price'])  # Preis um den Short Put zurückzukaufen
                exit_buy_price = float(buy_exit_df.iloc[0]['premium_option_price'])   # Preis um den Long Put zu verkaufen
                exit_stock_price = float(buy_exit_df.iloc[0]['close'])        # Preis der Aktie
                

                entry_sell_price = float(row['sell_last_option_price'])
                entry_buy_price = float(row['buy_last_option_price'])
                entry_stock_price = float(row['close'])

                # Strikes auslesen, um die Spread-Breite zu berechnen (Wichtig für das Risiko!)
                # Pass die Spaltennamen an, falls sie in deinem 'row' Objekt anders heißen
                strike_sell = float(row['sell_strike'])
                strike_buy = float(row['buy_strike'])
                spread_width = abs(strike_sell - strike_buy)

                # 2. Mathematische Berechnungen (Geldfluss-Perspektive)
                # Einstieg: Du kriegst Geld für den Sell, zahlst Geld für den Buy
                initial_cash_flow = entry_sell_price - entry_buy_price 

                # Schließen der Position: Du ZAHLST um den Sell zurückzukaufen (-), du ERHÄLTST Geld für den Buy (+)
                # Rechnerisch: exit_buy_price - exit_sell_price
                close_cash_flow = exit_buy_price - exit_sell_price

                # Der finale Gewinn/Verlust
                profit = initial_cash_flow + close_cash_flow

                # KORREKTUR: Das echte initiale Investment (Buying Power Reduction / Margin)
                # Bei Credit Spreads: Spread-Breite minus erhaltene Prämie
                # Bei Debit Spreads: Die gezahlte Prämie selbst
                if initial_cash_flow > 0:  # Credit Spread
                    bpr_capital = spread_width - initial_cash_flow
                else:                      # Debit Spread
                    bpr_capital = abs(initial_cash_flow)

                # Multiplikator für 100 Aktien pro Kontrakt (für die reale Depot-Anzeige)
                bpr_capital_total = bpr_capital * 100
                profit_total = profit * 100

                # KORREKTUR: Echter ROI bezogen auf das riskierte Kapital
                roi_pct = (profit / bpr_capital * 100) if bpr_capital > 0 else None


                # 3. VISUELLE DARSTELLUNG (Streamlit)
                st.markdown("### 📊 Trade-Analyse & Performance")

                # Oberste Reihe: Die wichtigsten harten Fakten als Key Performance Indicators (KPIs)
                kpi_cols = st.columns(4)
                with kpi_cols[0]:
                    st.metric("P/L Ergebnis", f"${profit_total:+.2f}", delta=f"${profit_total:+.2f}")
                with kpi_cols[1]:
                    if roi_pct is not None:
                        st.metric("Echter ROI (on Risk)", f"{roi_pct:.2f}%", delta=f"{roi_pct:.2f}%")
                    else:
                        st.metric("Echter ROI", "n/a")
                with kpi_cols[2]:
                    st.metric("Riskiertes Kapital (BPR)", f"${bpr_capital_total:.2f}", help="Das gebundene Kapital auf dem Konto")
                with kpi_cols[3]:
                    st.metric("Spread-Breite", f"${spread_width:.2f}")

                st.markdown("---")

                # Zweite Reihe: Verlauf des Trades (Einstieg vs. Ausstieg)
                comparison_cols = st.columns(3)

                with comparison_cols[0]:
                    st.subheader("🛫 1. Einstieg")
                    st.caption(f"Datum: {selected_date}")
                    st.metric("Initiale Prämie", f"{initial_cash_flow:+.2f} $", help="Positiv = Einnahme (Credit)")
                    st.text(f"Short Option: ${entry_sell_price:.2f}")
                    st.text(f"Long Option:  ${entry_buy_price:.2f}")

                with comparison_cols[1]:
                    st.subheader("🛬 2. Ausstieg")
                    st.caption(f"Datum: {compare_date}")
                    # Zeigt an, wie viel der Spread beim Schließen wert war (z.B. 0.01 $)
                    st.metric("Restwert Spread", f"${abs(close_cash_flow):.2f}", help="Idealerweise nahe 0$ bei Credit Spreads")
                    st.text(f"Short-Rückkauf: ${exit_sell_price:.2f}")
                    st.text(f"Long-Verkauf:  ${exit_buy_price:.2f}")

                with comparison_cols[2]:
                    st.subheader("💡 Trade Status")
                    days_held = (parse_date(compare_date) - parse_date(selected_date)).days
                    st.caption(f"Tage gehalten: {days_held}")
                    roi_annualized_pct = (
                        roi_pct * 365.0 / days_held
                        if roi_pct is not None and days_held > 0
                        else None
                    )
                    if profit > 0:
                        st.success(f"Gewinn-Trade!\nDu hast {roi_pct:.1f}% Rendite auf dein eingesetztes Kapital erzielt.")
                    elif profit < 0:
                        st.error(f"Verlust-Trade.\nVerlust: ${abs(profit_total):.2f}")
                    else:
                        st.info("Break-Even (±0 $)")
                    if roi_annualized_pct is not None:
                        st.metric("Annualisierter ROI", f"{roi_annualized_pct:.2f}%")
                    else:
                        st.write("Annualisierter ROI: n/a")

                # Breakeven berechnen (Short Strike minus eingenommene Prämie)
                breakeven_price = strike_sell - initial_cash_flow


                # --- SEKTION IN STREAMLIT ANLEGEN ---
                st.markdown("### 📈 Kursverlauf & Gewinnzonen-Analyse")

                # 1. Schnelle Text-Übersicht (Wo steht die Aktie?)
                zone_cols = st.columns(3)
                with zone_cols[0]:
                    st.metric("Aktienkurs beim Einstieg", f"${entry_stock_price:.2f}")
                with zone_cols[1]:
                    st.metric("Aktienkurs beim Ausstieg", f"${exit_stock_price:.2f}", 
                            delta=f"{((exit_stock_price - entry_stock_price)/entry_stock_price)*100:+.2f}%")
                with zone_cols[2]:
                    st.metric("Gewinnschwelle (Breakeven)", f"${breakeven_price:.2f}", 
                            help="Ab diesem Kurs am Verfallstag macht der Trade Gewinn.")

                # Erkennung, in welcher Zone der aktuelle Schlusskurs liegt
                st.markdown("**Aktueller Zonen-Status:**")
                if exit_stock_price >= strike_sell:
                    st.success(f"🟢 Maximaler Gewinnbereich! Der Kurs (${exit_stock_price:.2f}) steht über deinem Short-Strike (${strike_sell:.2f}).")
                elif breakeven_price < exit_stock_price < strike_sell:
                    st.info(f"🟡 Teilgewinn-Bereich! Der Kurs (${exit_stock_price:.2f}) hat den Short-Strike leicht unterschritten, liegt aber über dem Breakeven (${breakeven_price:.2f}).")
                else:
                    st.error(f"🔴 Verlustbereich. Der Kurs (${exit_stock_price:.2f}) ist unter den Breakeven (${breakeven_price:.2f}) gefallen.")


                # 2. VISUELLES DIAGRAMM (Kurs vs. Strikes & Breakeven)
                # Hinweis: Idealerweise übergibst du hier eine historische Liste von Kursen. 
                # Wenn du nur Einstieg und Ausstieg hast, zeichnen wir eine direkte Verbindungslinie.
                dates = [str(selected_date), str(compare_date)]
                stock_prices = [entry_stock_price, exit_stock_price]

                fig = go.Figure()

                # Linie für den Aktienkurs
                fig.add_trace(go.Scatter(
                    x=dates, y=stock_prices, 
                    mode='lines+markers', 
                    name='Aktienkurs',
                    line=dict(color='blue', width=4),
                    marker=dict(size=10)
                ))

                # Horizontale Linie: Short Strike (Gewinngrenze für Maximum)
                fig.add_hline(y=strike_sell, line_dash="dash", line_color="green", 
                            annotation_text=f"Short Strike Put (${strike_sell:.2f}) - Voller Gewinn darüber", 
                            annotation_position="top left")

                # Horizontale Linie: Breakeven (Die echte Nulllinie)
                fig.add_hline(y=breakeven_price, line_dash="dot", line_color="orange", 
                            annotation_text=f"Breakeven (${breakeven_price:.2f})", 
                            annotation_position="bottom left")

                # Horizontale Linie: Long Strike (Maximaler Verlust gedeckelt ab hier)
                fig.add_hline(y=strike_buy, line_dash="dash", line_color="red", 
                            annotation_text=f"Long Strike Put (${strike_buy:.2f}) - Max. Verlust darunter", 
                            annotation_position="bottom left")

                # Layout-Anpassungen für ein sauberes Dashboard-Design
                fig.update_layout(
                    title="Aktienkurs im Verhältnis zu den Options-Strikes",
                    xaxis_title="Datum / Verlauf",
                    yaxis_title="Aktienkurs in $",
                    legend_title="Legende",
                    margin=dict(l=20, r=20, t=40, b=20),
                    paper_bgcolor="rgba(0,0,0,0)", # Transparent für Streamlit Dark/Light Mode
                    plot_bgcolor="rgba(0,0,0,0)",
                    yaxis=dict(gridcolor='rgba(128,128,128,0.2)') # Leichte Gridlines
                )

                # Chart in Streamlit anzeigen
                st.plotly_chart(fig, use_container_width=True)
                # exit_sell_price = float(sell_exit_df.iloc[0]['premium_option_price'])
                # exit_buy_price = float(buy_exit_df.iloc[0]['premium_option_price'])

                # entry_sell_price = float(row['sell_last_option_price'])
                # entry_buy_price = float(row['buy_last_option_price'])
                # initial_cash_flow = entry_sell_price - entry_buy_price
                # current_close_cashflow = exit_buy_price - exit_sell_price
                # profit = initial_cash_flow + current_close_cashflow
                # initial_investment = abs(initial_cash_flow)
                # roi_pct = (
                #     profit / initial_investment * 100
                #     if initial_investment != 0
                #     else None
                # )

                # comparison_cols = st.columns(3)
                # with comparison_cols[0]:
                #     st.metric("Einstiegsdatum", str(selected_date))
                #     st.metric(
                #         "Initiale Prämie",
                #         f"{initial_cash_flow:+.2f} $",
                #         help="Positiv = Prämie erhalten, Negativ = Prämie bezahlt"
                #     )
                #     st.metric("Einstieg Sell", f"${entry_sell_price:.2f}")
                #     st.metric("Einstieg Buy", f"${entry_buy_price:.2f}")

                # with comparison_cols[1]:
                #     st.metric("Vergleichsdatum", str(compare_date))
                #     st.metric("Schluss Sell", f"${exit_sell_price:.2f}")
                #     st.metric("Schluss Buy", f"${exit_buy_price:.2f}")
                #     st.metric("Aktueller Spreadwert", f"${current_close_cashflow:.2f}")

                # with comparison_cols[2]:
                #     st.metric("P/L bei Schließung", f"${profit:.2f}")
                #     if roi_pct is not None:
                #         st.metric("ROI", f"{roi_pct:.2f}%")
                #     else:
                #         st.write("ROI: n/a")
    else:
        st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die Details der einzelnen Legs zu sehen.")

# Show documentation
with st.expander("📖 Documentation - Fields Overview", expanded=False):
    st.markdown(get_spreads_documentation())