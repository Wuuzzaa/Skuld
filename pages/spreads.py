import logging
import streamlit as st
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.spreads_calculation import calc_spreads

def get_expiration_type(expiration_date):
    date = pd.to_datetime(expiration_date)
    day_of_week = date.dayofweek  # 4 = Freitag

    if day_of_week == 4:  # Freitag
        # Prüfe, ob es der dritte Freitag im Monat ist
        first_day_of_month = date.replace(day=1)
        # Finde alle Freitage im Monat
        offset = (4 - first_day_of_month.dayofweek) % 7
        third_friday = first_day_of_month + pd.Timedelta(days=offset + 14)

        if date.day == third_friday.day:
            return "Monthly"
        else:
            return "Weekly"
    else:
        return "Daily"

# enable logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.debug(f"Start Page: {__name__}")

# Page header
st.title("Spreads")

# Main configuration section
col_epiration_date, col_delta_target, col_spread_width, col_option_type = st.columns(4)

# expiration date
with col_epiration_date:
    # Initialize the session state for checkboxes. Default only monthly options
    if 'show_monthly' not in st.session_state:
        st.session_state.show_monthly = True
    if 'show_weekly' not in st.session_state:
        st.session_state.show_weekly = False
    if 'show_daily' not in st.session_state:
        st.session_state.show_daily = False

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
    dates_df = select_into_dataframe(sql_file_path=sql_file_path)

    # Filter dates_df based on checkbox states
    filtered_dates_df = dates_df[
        (dates_df.apply(lambda row: get_expiration_type(row['expiration_date']) == "Monthly", axis=1) & st.session_state.show_monthly) |
        (dates_df.apply(lambda row: get_expiration_type(row['expiration_date']) == "Weekly", axis=1) & st.session_state.show_weekly) |
        (dates_df.apply(lambda row: get_expiration_type(row['expiration_date']) == "Daily", axis=1) & st.session_state.show_daily)
    ]

    # dte labels ("5 DTE - Friday 2026-01-16 - Monthly/Weekly/Daily")
    dte_labels = filtered_dates_df.apply(
        lambda row: (
            f"{int(row['days_to_expiration'])} DTE - "
            f"{pd.to_datetime(row['expiration_date']).strftime('%A')}  "
            f"{row['expiration_date']} - "
            f"{get_expiration_type(row['expiration_date'])}"
        ),
        axis=1
    ).tolist()

    # selectbox with dte labels
    selected_label = st.selectbox("Expiration Date", dte_labels)

    # Checkboxes for filtering
    st.checkbox(
        "Show Monthly",
        key="show_monthly"
    )
    st.checkbox(
        "Show Weekly",
        key="show_weekly"
    )
    st.checkbox(
        "Show Daily",
        key="show_daily"
    )

    # extract selected expiration date from dte label
    selected_index = dte_labels.index(selected_label)
    expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']
    logging.debug(f"extract selected expiration date from dte label expiration_date: {expiration_date}")

# delta target
with col_delta_target:
    delta_target = st.number_input("Delta Target", min_value=0.0, max_value=1.0, value=0.2, step=0.01)

# spread width
with col_spread_width:
    spread_width = st.number_input("Spread Width", min_value=1, max_value=20, value=5, step=1)

with col_option_type:
    option_type = st.selectbox("Option Type", ["put", "call"])

# calculate the spread values with a loading indicator
with st.spinner("Calculating spreads..."):
    logging.debug(f"expiration_date: {expiration_date}")
    logging.debug(f"option_type: {option_type}")
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path, params={
        "expiration_date": expiration_date,
        "option_type": option_type
    })
    logging.debug(f"df: {df.head()}")

    spreads_df = calc_spreads(df, delta_target, spread_width)

# Dynamically extract unique values for symbol and option_type from calculated spreads_df
if spreads_df.empty:
    st.warning("No spreads found for the selected criteria.")
    st.stop()

unique_symbols = sorted(spreads_df['symbol'].unique())
unique_option_types = sorted(spreads_df['option_type'].unique())

st.divider()

# Advanced filters
st.markdown("##### Advanced Filters")
col_ivr, col_ivp, col_open_interest, col_profit_bpr = st.columns(4)

# IVR Filter
with col_ivr:
    ivr_min = float(spreads_df['ivr'].min())
    ivr_max = float(spreads_df['ivr'].max())
    if ivr_min == ivr_max:
        st.text_input("IVR", value=f"{ivr_min:.2f}", disabled=True)
        ivr_range = (ivr_min, ivr_max)
    else:
        # Default minimum value of 0.3
        default_min = max(ivr_min, 0.3)
        ivr_range = st.slider(
            "IVR Range",
            min_value=ivr_min,
            max_value=ivr_max,
            value=(default_min, ivr_max),
            step=0.01
        )

# IVP Filter
with col_ivp:
    ivp_min = float(spreads_df['ivp'].min())
    ivp_max = float(spreads_df['ivp'].max())
    if ivp_min == ivp_max:
        st.text_input("IVP", value=f"{ivp_min:.2f}", disabled=True)
        ivp_range = (ivp_min, ivp_max)
    else:
        # Default minimum value of 0.3
        default_min = max(ivp_min, 0.3)
        ivp_range = st.slider(
            "IVP Range",
            min_value=ivp_min,
            max_value=ivp_max,
            value=(default_min, ivp_max),
            step=0.01
        )

# Open Interest Filter
with col_open_interest:
    oi_min = int(spreads_df['open_intrest'].min())
    oi_max = int(spreads_df['open_intrest'].max())
    if oi_min == oi_max:
        st.text_input("Open Interest", value=f"{oi_min}", disabled=True)
        oi_threshold = oi_min
    else:
        # Default minimum value of 100
        default_oi = max(oi_min, 100)
        oi_threshold = st.number_input(
            "Min Open Interest",
            min_value=oi_min,
            max_value=oi_max,
            value=default_oi,
            step=100
        )

# Profit to BPR Filter
with col_profit_bpr:
    profit_bpr_min = float(spreads_df['profit_to_bpr'].min())
    profit_bpr_max = float(spreads_df['profit_to_bpr'].max())
    if profit_bpr_min == profit_bpr_max:
        st.text_input("Profit/BPR", value=f"{profit_bpr_min:.3f}", disabled=True)
        profit_bpr_threshold = profit_bpr_min
    else:
        # Default minimum value of 0.1, but not exceeding max
        default_profit = min(max(profit_bpr_min, 0.1), profit_bpr_max)
        profit_bpr_threshold = st.number_input(
            "Min Profit/BPR",
            min_value=profit_bpr_min,
            max_value=profit_bpr_max,
            value=default_profit,
            step=0.01,
            format="%.3f"
        )

st.divider()

# Apply filters
filtered_df = spreads_df.copy()

# Apply symbol filter
if symbol != "All Symbols":
    filtered_df = filtered_df[filtered_df['symbol'] == symbol]

# Apply option type filter
filtered_df = filtered_df[filtered_df['option_type'] == option_type]

# Apply IVR filter
filtered_df = filtered_df[
    (filtered_df['ivr'] >= ivr_range[0]) &
    (filtered_df['ivr'] <= ivr_range[1])
    ]

# Apply IVP filter
filtered_df = filtered_df[
    (filtered_df['ivp'] >= ivp_range[0]) &
    (filtered_df['ivp'] <= ivp_range[1])
    ]

# Apply Open Interest filter
filtered_df = filtered_df[filtered_df['open_intrest'] >= oi_threshold]

# Apply Profit to BPR filter
filtered_df = filtered_df[filtered_df['profit_to_bpr'] >= profit_bpr_threshold]

# Results summary
col_results, col_spacer = st.columns([1, 3])
with col_results:
    st.metric(
        label="Results",
        value=f"{len(filtered_df)}",
        delta=f"{len(filtered_df) - len(spreads_df)} from total"
    )

st.markdown("### Results")

# optionstrat_url is only on the spread page so declare it here
column_config = {
    "optionstrat_url": st.column_config.LinkColumn(
        label="",
        help="OptionStrat",
        display_text="🎯",
    )
}

# show final dataframe
page_display_dataframe(filtered_df, page='spreads', symbol_column='symbol', column_config=column_config)