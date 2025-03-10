import time
from datetime import datetime

import streamlit as st
import pandas as pd
from src.spreads_calculation import get_spreads
from src.util import get_option_expiry_dates

# Titel
st.subheader("Spreads")

# get a default date
default_expiration_date = str(get_option_expiry_dates()[0])
default_expiration_date = str(datetime.strptime(default_expiration_date, "%Y%m%d").strftime("%Y-%m-%d"))

# Create three columns for compact input arrangement
col1, col2, col3 = st.columns(3)

with col1:
    expiration_date = str(st.date_input("Expiration Date", value=default_expiration_date))
with col2:
    delta_target = st.number_input("Delta Target", min_value=0.0, max_value=1.0, value=0.2, step=0.01)
with col3:
    spread_width = st.number_input("Spread Width", min_value=1, max_value=20, value=5, step=1)

# filter the dataframe and calculate the spread values... with loading indicator
with st.status("Calculating... Please wait.", expanded=True) as status:
    spreads_df = get_spreads(st.session_state['df'], expiration_date, delta_target, spread_width)
    status.update(label="Calculation complete!", state="complete", expanded=True)


# show the spreads
st.dataframe(get_spreads(st.session_state['df'], expiration_date, delta_target, spread_width), use_container_width=True)
