import time
from datetime import datetime
import streamlit as st
import pandas as pd
from src.iron_condor_calculation import get_iron_condors
from src.util import get_option_expiry_dates
from src.custom_logging import *

# Titel
st.subheader("Iron Condors")

# Create three columns for compact input arrangement
col_epiration_date, col_delta_target, col_spread_width = st.columns(3)

with col_epiration_date:
    # https://docs.streamlit.io/develop/api-reference/widgets/st.date_input

    # Exipraton dates with selectbox
    expiration_dates = [
        datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d")
        for date
        in get_option_expiry_dates()
    ]

    expiration_date = st.selectbox("Expiration Date", expiration_dates)

with col_delta_target:
    delta_target = st.number_input("Delta Target", min_value=0.0, max_value=1.0, value=0.2, step=0.01)
with col_spread_width:
    spread_width = st.number_input("Spread Width", min_value=1, max_value=20, value=5, step=1)

# filter the dataframe and calculate the spread values... with loading indicator
with st.status("Calculating... Please wait.", expanded=True) as status:
    ic_df = get_iron_condors(st.session_state['df'], expiration_date, delta_target, spread_width)
    status.update(label="Calculation complete!", state="complete", expanded=True)

# show the spreads
log_info(f"Iron Condors calculated for: {expiration_date} and delta {delta_target} with spread width {spread_width}")
st.dataframe(ic_df, use_container_width=True)
