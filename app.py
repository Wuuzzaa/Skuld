import streamlit as st
import pandas as pd
from config import *
from src.custom_logging import show_log_messages, log_info # Adjust the module name as needed

# streamlit run C:\Users\jonas\PycharmProjects\Skuld\app.py

# Set the layout of the page to wide
st.set_page_config(layout="wide")

# Title of the app
st.title("SKULD - Option Viewer")

# Load the DataFrame from a Feather file
df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
log_info(f"File loaded successfully: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")

# Create tabs for the application
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "Complete DataFrame",
        "Filtered View",
        "Analyst Prices",
        "Logs"
    ]
)

with tab1:
    st.subheader("Complete DataFrame")
    st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Filtered View")
    st.sidebar.header("Filter Options")

    """ Filter for numeric columns """
    num_cols = df.select_dtypes(include=['float64', 'int64']).columns
    filtered_df = df.copy()
    for col in num_cols:
        min_val, max_val = st.sidebar.slider(
            f"Filter for {col}",
            float(df[col].min()),
            float(df[col].max()),
            (float(df[col].min()), float(df[col].max())),
        )
        filtered_df = filtered_df[(filtered_df[col] >= min_val) & (filtered_df[col] <= max_val)]

    """ Filter for categorical columns """
    cat_cols = df.select_dtypes(include=['object']).columns
    for col in cat_cols:
        selected = st.sidebar.multiselect(f"Select values for {col}", df[col].unique())
        if selected:
            filtered_df = filtered_df[filtered_df[col].isin(selected)]

    st.dataframe(filtered_df, use_container_width=True)

with tab3:
    st.subheader("Analyst Prices")

    """ Create a DataFrame for Analyst Prices tab """
    df_tab3 = df[
        [
            "symbol",
            "close",
            "analyst_mean_target",
            "recommendation",
            "Recommend.All",
            "target-close$",
            "target-close%"
        ]
    ].drop_duplicates().reset_index(drop=True)

    """ Rename columns for a better display """
    df_tab3 = df_tab3.rename(
        columns={
            "symbol": "Symbol",
            "close": "Price",
            "analyst_mean_target": "Mean Analyst Target",
            "recommendation": "Indicators Recommendation",
            "Recommend.All": "Recommendation Strength (-1 to 1)",
            "target-close$": "Difference ($) analyst target and price",
            "target-close%": "Difference (%) analyst target and price"
        }
    )

    st.dataframe(df_tab3, use_container_width=True)

with tab4:
    st.subheader("Logs")
    """ Display all collected log messages """
    show_log_messages()
