import time
from datetime import datetime
import streamlit as st
import pandas as pd
from src.spreads_calculation import get_spreads
from src.util import get_option_expiry_dates
from src.custom_logging import *

# Titel
st.subheader("Spreads")

# Create layout with multiple columns
col_epiration_date, col_delta_target, col_spread_width = st.columns(3)

# expiration date
with col_epiration_date:
    # Expiration dates with selectbox
    expiration_dates = [
        datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d")
        for date in get_option_expiry_dates()
    ]
    expiration_date = st.selectbox("Expiration Date", expiration_dates)

# delta target
with col_delta_target:
    delta_target = st.number_input("Delta Target", min_value=0.0, max_value=1.0, value=0.2, step=0.01)

# spread width
with col_spread_width:
    spread_width = st.number_input("Spread Width", min_value=1, max_value=20, value=5, step=1)

# Filter the dataframe and calculate the spread values with loading indicator
with st.status("Calculating... Please wait.", expanded=True) as status:
    spreads_df = get_spreads(st.session_state['df'], expiration_date, delta_target, spread_width)
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
    option_type = st.selectbox("Option Type", ["Put and Call"] + unique_option_types)

# Apply filters if specific values are selected
# let it on "All" "" does not work
if symbol != "All Symbols":
    spreads_df = spreads_df[spreads_df['symbol'] == symbol]

if option_type != "Put and Call":
    spreads_df = spreads_df[spreads_df['option_type'] == option_type]

# Show the filtered spreads
log_info(f"Spreads calculated for: {expiration_date}, delta {delta_target}, spread width {spread_width}, symbol {symbol}, option type {option_type}")
st.dataframe(spreads_df, use_container_width=True)
