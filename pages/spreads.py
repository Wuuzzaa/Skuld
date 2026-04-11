import logging
import os
import streamlit as st
import pandas as pd
from pandas.tseries.holiday import AbstractHolidayCalendar, Holiday, nearest_workday, GoodFriday
from config import PATH_DATABASE_QUERY_FOLDER
from pages.documentation_text.spreads_page_doc import get_spreads_documentation
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.spreads_calculation import get_page_spreads

# ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)



class USOptionHolidayCalendar(AbstractHolidayCalendar):
    rules = [
        Holiday("New Years Day", month=1, day=1, observance=nearest_workday),
        Holiday("Martin Luther King Jr. Day", month=1, day=1, offset=pd.DateOffset(weekday=0, weeks=2)),
        Holiday("Presidents Day", month=2, day=1, offset=pd.DateOffset(weekday=0, weeks=2)),
        GoodFriday,
        Holiday("Memorial Day", month=5, day=31, offset=pd.DateOffset(weekday=0, weeks=-1)),
        Holiday("Juneteenth", month=6, day=19, observance=nearest_workday),
        Holiday("July 4th", month=7, day=4, observance=nearest_workday),
        Holiday("Labor Day", month=9, day=1, offset=pd.DateOffset(weekday=0, weeks=0)),
        Holiday("Thanksgiving", month=11, day=1, offset=pd.DateOffset(weekday=3, weeks=3)),
        Holiday("Christmas", month=12, day=25, observance=nearest_workday),
    ]


def get_expiration_type(expiration_date):
    date = pd.to_datetime(expiration_date)

    # 1. Berechne den theoretischen 3. Freitag im Monat
    first_day_of_month = date.replace(day=1)
    # offset zum ersten Freitag
    offset = (4 - first_day_of_month.dayofweek) % 7
    third_friday = first_day_of_month + pd.Timedelta(days=offset + 14)

    # 2. Prüfe auf Feiertage (NYSE)
    cal = USOptionHolidayCalendar()
    # NYSE Feiertage sind fix, wir prüfen das Jahr des aktuellen Datums
    holidays = cal.holidays(start=date.replace(month=1, day=1), end=date.replace(month=12, day=31))

    # Wenn der 3. Freitag ein Feiertag ist, verschiebt sich der Monthly auf den Werktag davor (Donnerstag)
    if third_friday in holidays:
        actual_monthly_expiry = third_friday - pd.Timedelta(days=1)
    else:
        actual_monthly_expiry = third_friday

    if date == actual_monthly_expiry:
        return "Monthly"

    # Wenn es kein Monthly ist, prüfen ob es ein Freitag ist (Standard Weekly)
    # ODER ein Donnerstag, falls der Freitag ein Feiertag ist
    if date.dayofweek == 4:
        return "Weekly"

    # Wenn es ein Donnerstag ist, prüfe ob der Freitag darauf ein Feiertag ist
    if date.dayofweek == 3:
        next_day = date + pd.Timedelta(days=1)
        if next_day in holidays:
            return "Weekly"

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
        min_day_volume = st.number_input(
            "Min dayvolume",
            min_value=0,
            value=20,
            step=1
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
        max_sell_iv = st.number_input(
            "Max sell iv",
            min_value=0.0,
            value=0.9,
            step=0.05,
            format="%.2f"
        )

    # fourth row
    col13, col14, col15, col16 = st.columns(4)
    #col13 = st.columns(1)[0] # [0] because TypeError: 'list' object does not support the context manager protocol when only one column is used access the element directly

    with col13:
        st.checkbox(
            "Show only spreads with no earnings till expiration",
            key="show_only_spreads_with_no_earnings_till_expiration"
        )

    with col14:
        min_max_profit = st.number_input(
            "Min Max Profit",
            min_value=0.0,
            value=80.0,
            step=1.0,
            format="%.2f"
        )

    with col15:
        min_iv_rank = st.number_input(
            "Min iv rank",
            min_value=0,
            max_value=100,
            value=0,
            step=1
        )

    with col16:
        min_iv_percentile = st.number_input(
            "Min iv percentile",
            min_value=0,
            max_value=100,
            value=0,
            step=1
        )

# calculate the spread values with a loading indicator
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

# only spreads with no earnings till expiration

# helper variables
today = pd.Timestamp.now().normalize()
expiration_date_ts = pd.Timestamp(expiration_date)

if st.session_state.show_only_spreads_with_no_earnings_till_expiration:
    filtered_df = filtered_df[
        ~(
                (filtered_df['earnings_date'] > today) &
                (filtered_df['earnings_date'] < expiration_date_ts)
        )
    ]

    # Konvertiere die 'earnings_date'-Spalte in ein datetime-Objekt
    filtered_df['earnings_date'] = pd.to_datetime(filtered_df['earnings_date'])

    # Formatiere die 'earnings_date'-Spalte im gewünschten Format
    filtered_df['earnings_date'] = filtered_df['earnings_date'].dt.strftime('%d.%m.%Y')

# min_sell_iv
filtered_df = filtered_df[filtered_df['sell_iv'] >= min_sell_iv]

# max_sell_iv
filtered_df = filtered_df[filtered_df['sell_iv'] <= max_sell_iv]

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