import streamlit as st
import pandas as pd
from config import *
from src.google_drive_download import load_updated_data
from src.custom_logging import show_log_messages, log_info # Adjust the module name as needed

# Set the layout of the page to wide
st.set_page_config(layout="wide")

# Title of the app
st.title("SKULD - Option Viewer")


# load dataframe
@st.cache_data
def load_dataframe():
    df = load_updated_data()
    return df


if 'df' not in st.session_state:
    st.session_state['df'] = load_dataframe()
    st.success(f"File loaded successfully: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")

# Define pages
total_dataframe = st.Page("pages/total_dataframe.py", title="Total Data")
filtered_dataframe = st.Page("pages/filtered_dataframe.py", title="Filtered Data")
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")
log_messages = st.Page("pages/log_messages.py", title="Log messages")

# Set up navigation
page = st.navigation([total_dataframe, filtered_dataframe, analyst_prices,log_messages])

# Run the selected page
page.run()
