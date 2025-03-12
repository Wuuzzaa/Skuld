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
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")
spreads = st.Page("pages/spreads.py", title="Spreads")
log_messages = st.Page("pages/log_messages.py", title="Log messages")

# Set up navigation
page = st.navigation(
    [
        total_dataframe,
        filtered_dataframe,
        analyst_prices,
        spreads,
        log_messages
    ]
)

# Run the selected page
page.run()
