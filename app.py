import streamlit as st
import pandas as pd
from config import *

# Layout
st.set_page_config(layout="wide")

# Titel
st.title("SKULD - Option Viewer")

# load dataframe
@st.cache_data
def load_dataframe():
    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    return df


if 'df' not in st.session_state:
    st.session_state['df'] = load_dataframe()
    st.success(f"File loaded successfully: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")

# Define pages
gesamter_dataframe = st.Page("pages/total_dataframe.py", title="Total Data")
gefilterte_ansicht = st.Page("pages/filtered_dataframe.py", title="Filtered Data")
analyst_prices = st.Page("pages/analyst_prices.py", title="Analyst Prices")

# Set up navigation
page = st.navigation([gesamter_dataframe, gefilterte_ansicht, analyst_prices])

# Run the selected page
page.run()
