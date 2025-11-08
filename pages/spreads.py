import streamlit as st
from src.database import select_into_dataframe
from src.page_display_dataframe import page_display_dataframe
from src.spreads_calculation import calc_spreads
from config import *

# Titel
st.subheader("Spreads")

# Create a layout with multiple columns
col_epiration_date, col_delta_target, col_spread_width = st.columns(3)

# expiration date
with col_epiration_date:
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
    dates_df = select_into_dataframe(sql_file_path=sql_file_path)

    # dte labels  ("5 DTE - 2025-01-15")
    dte_labels = dates_df.apply(
        lambda row: f"{int(row['days_to_expiration'])} DTE  {row['expiration_date']}",
        axis=1
    ).tolist()

    # selectbox with dte labels
    selected_label = st.selectbox("Expiration Date", dte_labels)

    # extract selected expiration date from dte label
    selected_index = dte_labels.index(selected_label)
    expiration_date = dates_df.iloc[selected_index]['expiration_date']

# delta target
with col_delta_target:
    delta_target = st.number_input("Delta Target", min_value=0.0, max_value=1.0, value=0.2, step=0.01)

# spread width
with col_spread_width:
    spread_width = st.number_input("Spread Width", min_value=1, max_value=20, value=5, step=1)

# calculate the spread values with a loading indicator
with st.status("Calculating... Please wait.", expanded=True) as status:
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'spreads_input.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path, params={"expiration_date": expiration_date})
    spreads_df = calc_spreads(df, delta_target, spread_width)
    status.update(label="Calculation complete!", state="complete", expanded=True)

# Dynamically extract unique values for symbol and option_type from calculated spreads_df
unique_symbols = sorted(spreads_df['symbol'].unique())
unique_option_types = sorted(spreads_df['option_type'].unique())

col_symbol, col_option_type = st.columns(2)

# symbol
with col_symbol:
    symbol = st.selectbox("Symbol", ["All Symbols"] + unique_symbols)

# option type
with col_option_type:
    option_type = st.selectbox("Option Type", unique_option_types)

# Apply filters if specific values are selected
# let it on "All" "" does not work
if symbol != "All Symbols":
    spreads_df = spreads_df[spreads_df['symbol'] == symbol]

# show only the calculated option type
spreads_df = spreads_df[spreads_df['option_type'] == option_type]

# optionstrat_url is only on the spread page so declare it here
column_config = {
    "optionstrat_url":  st.column_config.LinkColumn(
        label="",
        help="OptionStrat",
        display_text="🎯",
    )
}

# show final dataframe
page_display_dataframe(spreads_df, symbol_column='symbol', column_config=column_config)
