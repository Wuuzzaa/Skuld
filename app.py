import streamlit as st
import pandas as pd
from config import *
from src.google_drive_download import load_updated_data
from src.custom_logging import *
import sys

# Check if "--local" is passed as a command-line argument
# start in terminal with: streamlit run app.py -- --local
# note the -- --local NOT --local this would be interpreted as a streamlit argument
use_local_data = "--local" in sys.argv

# Layout
st.set_page_config(layout="wide")

# Titel
st.title("SKULD - Option Viewer")


# load dataframe
@st.cache_data
def load_dataframe():
    # Local Mode
    if use_local_data:
        log_write("Using local dataset instead of Google Drive data!")
        return pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)

    # Online Mode with Googledrive data
    else:
        return load_updated_data()


if 'df' not in st.session_state:
    st.session_state['df'] = load_dataframe()
    st.success(f"File loaded successfully: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")

# Define pages
total_dataframe = st.Page("pages/total_dataframe.py", title="Total Data")
filtered_dataframe = st.Page("pages/filtered_dataframe.py", title="Filtered Data")
iv_filter = st.Page("pages/iv_filter.py", title="IV Filter")
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")
spreads = st.Page("pages/spreads.py", title="Spreads")
iron_condors = st.Page("pages/iron_condors.py", title="Iron Condors")
multi_indicator_direction = st.Page("pages/strategy_multi_indicator_score_direction.py", title="Multi-Indicator Direction")
log_messages = st.Page("pages/log_messages.py", title="Log messages")
dividend_page = st.Page("pages/dividend_page.py", title="Dividend Page")
documentation = st.Page("pages/documentation.py", title="Documentation")
marrieds = st.Page("pages/married_put_analysis.py", title="Married Puts")


# Set up navigation
page = st.navigation(
    [
        total_dataframe,
        filtered_dataframe,
        iv_filter,
        analyst_prices,
        spreads,
        iron_condors,
        multi_indicator_direction,
        log_messages,
        dividend_page,
        documentation, 
     
        marrieds
    ]
)

# Run the selected page
page.run()
