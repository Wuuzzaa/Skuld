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

# ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)


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
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Page header
st.title("Spreads")

# filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    # Initialize session state for checkboxes
    if 'show_monthly' not in st.session_state:
        st.session_state.show_monthly = True
    if 'show_weekly' not in st.session_state:
        st.session_state.show_weekly = False
    if 'show_daily' not in st.session_state:
        st.session_state.show_daily = False
    if 'show_only_positiv_expected_value' not in st.session_state:
        st.session_state.show_only_positiv_expected_value = True
    if 'show_only_spreads_with_no_earnings_till_expiration' not in st.session_state:
        st.session_state.show_only_spreads_with_no_earnings_till_expiration = True


    # first row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_into_dataframe(sql_file_path=sql_file_path)

        # Filter dates_df based on checkbox states
        filtered_dates_df = dates_df[
            (dates_df.apply(lambda row: get_expiration_type(row['expiration_date']) == "Monthly",
                            axis=1) & st.session_state.show_monthly) |
            (dates_df.apply(lambda row: get_expiration_type(row['expiration_date']) == "Weekly",
                            axis=1) & st.session_state.show_weekly) |
            (dates_df.apply(lambda row: get_expiration_type(row['expiration_date']) == "Daily",
                            axis=1) & st.session_state.show_daily)
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

        # extract selected expiration date from dte label
        selected_index = dte_labels.index(selected_label)
        expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']
        logging.debug(f"extract selected expiration date from dte label expiration_date: {expiration_date}")

    with col2:
        delta_target = st.number_input(
            "Delta Target",
            min_value=0.0,
            max_value=1.0,
            value=0.2,
            step=0.01
        )

    with col3:
        spread_width = st.number_input(
            "Spread Width",
            min_value=1,
            max_value=20,
            value=5,
            step=1
        )

    with col4:
        option_type = st.selectbox("Option Type", ["put", "call"])

    # second row
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


    # third row
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        min_max_profit = st.number_input(
            "Min Max Profit",
            min_value=0.0,
            value=80.0,
            step=1.0,
            format="%.2f"
        )

    with col10:
        min_open_interest = st.number_input(
            "Min Open Interest",
            min_value=0,
            value=100,
            step=100
        )

    with col11:
        min_sell_iv = st.number_input(
            "Min sell iv",
            min_value=0.0,
            value=0.3,
            step=0.05,
            format="%.2f"
        )

    with col12:
        st.checkbox(
            "Show only spreads with no earnings till expiration",
            key="show_only_spreads_with_no_earnings_till_expiration"
        )

# calculate the spread values with a loading indicator
with st.spinner("Calculating spreads..."):
    params = {
        "expiration_date": expiration_date,
        "option_type": option_type,
        "delta_target": delta_target,
        "min_open_interest": min_open_interest,
        "spread_width": spread_width
    }

    logging.debug(f"params: {params}")

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path, params=params)
    logging.debug(f"df: {df.head()}")

    spreads_df = get_page_spreads(df)
    logging.debug(f"spreads_df: {spreads_df.head()}")

# Apply spreadfilter
filtered_df = spreads_df.copy()

# min_max_profit
filtered_df = filtered_df[filtered_df['max_profit'] >= min_max_profit]

# only positive expected value
if st.session_state.show_only_positiv_expected_value:
    filtered_df = filtered_df[filtered_df['expected_value'] >= 0]

# Tag heute als Timestamp
tag_heute = pd.Timestamp.now().normalize()

# Konvertiere expiration_date zu Timestamp
expiration_date_ts = pd.Timestamp(expiration_date)

# Filter anwenden
if st.session_state.show_only_spreads_with_no_earnings_till_expiration:
    filtered_df = filtered_df[
        ~(
            (filtered_df['earnings_date'] > tag_heute) &
            (filtered_df['earnings_date'] < expiration_date_ts)
        )
    ]
# min_sell_iv
filtered_df = filtered_df[filtered_df['sell_iv'] >= min_sell_iv]

# After the filters reset the index to ensure the zebra style works on the dataframe
filtered_df.reset_index(drop=True, inplace=True)

st.markdown(f"### {len(filtered_df)} Results")

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


# show documentation
with st.expander("📖 Dokumentation - Feldübersicht", expanded=False):
    st.markdown(get_spreads_documentation())