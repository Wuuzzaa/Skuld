import streamlit as st
import pandas as pd
import os
from st_aggrid import AgGrid, GridOptionsBuilder

# Import the force_data_download function from your module
from src.dividend_radar import force_data_download  # Adjust module path accordingly
from config import PATH_DIVIDEND_RADAR  # Path to the dividend file (e.g., dividend_data.feather)

# Sidebar: custom threshold inputs for each group
custom_thresh_group1 = st.sidebar.number_input("Custom Threshold for Group 1 (Div-Yield ≥ 3)", value=14, step=1)
custom_thresh_group2 = st.sidebar.number_input("Custom Threshold for Group 2 (Div-Yield < 3)", value=15, step=1)

# Sidebar: Instead of two individual toggle buttons, a multiselect is used here
selected_groups = st.sidebar.multiselect(
    "show chowder Numbers:",
    options=["Group 1", "Group 2"],
    default=["Group 1", "Group 2"]
)

# Sidebar: button to force data download
if st.sidebar.button("Force Data Download"):
    force_data_download(PATH_DIVIDEND_RADAR)
    st.sidebar.success("Force data download completed.")

# Sidebar: radio to select display mode
display_option = st.sidebar.radio(
    "Select display mode:",
    ["Show Only Option Strategy Relevant Data", "Show Full Dividend File"]
)

# Determine available columns based on display mode
if display_option == "Show Full Dividend File":
    if os.path.exists(PATH_DIVIDEND_RADAR):
        try:
            full_dividend_df_temp = pd.read_feather(PATH_DIVIDEND_RADAR)
            full_dividend_df_temp.columns = full_dividend_df_temp.columns.str.lower().str.strip()
            available_columns = list(full_dividend_df_temp.columns)
        except Exception as e:
            st.sidebar.error("Error reading full dividend file: " + str(e))
            available_columns = []
    else:
        available_columns = []
else:
    if "df" in st.session_state:
        available_columns = list(st.session_state["df"].columns)
    else:
        available_columns = []

default_options = [col.lower() for col in ["symbol", "Div-Yield", "Chowder-Number", "Fair-Value"]]
default_columns = [col for col in available_columns if col in default_options]

selected_columns = st.sidebar.multiselect("Select columns to display", options=available_columns, default=default_columns)
if not selected_columns:
    st.error("Please select at least one column.")
    st.stop()

# Page Title and Subheader
st.subheader("Dividenden-Radar")
tooltips = {"symbol": "Stock symbol"}


st.markdown("""
### What Is the Chowder Number?

The **Chowder Number** is a screening metric popular in the dividend growth investing community.
It is typically calculated as the sum of a stock's **current dividend yield** and its **5-year average dividend yield**.
Here, the 5-year average dividend yield is used as a proxy for the dividend growth rate.

**Rules of Thumb:**  
- **Group 1:** For stocks with a dividend yield of **3% or higher**, a Chowder Number above the configured threshold 14 is preferred.  
- **Group 2:** For stocks with a dividend yield **below 3**, a Chowder Number above the configured threshold 15 is considered favorable.

This metric helps quickly identify dividend-paying stocks that may warrant further research.
""")

side_bar_config = {
    "toolPanels": [
        {
            "id": "columns",
            "labelDefault": "Columns",
            "labelKey": "columns",
            "iconKey": "columns",
            "toolPanel": "agColumnsToolPanel"
        }
    ],
    "defaultToolPanel": "columns"
}

default_filter_params = {
    'filter': True,
    'sortable': True,
    'resizable': True,
    'floatingFilter': True,
    'filterParams': {
        'filterOptions': ['contains', 'notContains', 'equals', 'notEqual', 'startsWith', 'endsWith']
    }
}

if display_option == "Show Full Dividend File":
    st.subheader("Full Dividend File")
    if os.path.exists(PATH_DIVIDEND_RADAR):
        try:
            full_dividend_df = pd.read_feather(PATH_DIVIDEND_RADAR)
            full_dividend_df.columns = full_dividend_df.columns.str.lower().str.strip()
            display_columns = [col for col in selected_columns if col in full_dividend_df.columns]
            if "symbol" in full_dividend_df.columns and "symbol" not in display_columns:
                display_columns.insert(0, "symbol")
            if not display_columns:
                st.warning("None of the selected columns are available in the full dividend file. Displaying all columns instead.")
                full_display = full_dividend_df
            else:
                full_display = full_dividend_df[display_columns]
            gb_full = GridOptionsBuilder.from_dataframe(full_display)
            gb_full.configure_default_column(**default_filter_params)
            gb_full.configure_side_bar(side_bar_config)
            for col in full_display.columns:
                if col in tooltips:
                    gb_full.configure_column(col, headerTooltip=tooltips[col])
                else:
                    gb_full.configure_column(col)
            gridOptions_full = gb_full.build()
            AgGrid(full_display, gridOptions=gridOptions_full, key=f"full_dividend_{'_'.join(selected_columns)}",
                   enable_enterprise_modules=False, fit_columns_on_grid_load=True)
        except Exception as e:
            st.error(f"AgGrid display error for full dividend file: {e}")
            st.table(full_dividend_df)
    else:
        st.warning("Full dividend file not found. Please ensure the dividend data has been downloaded.")
else:
    # Show Only Option Strategy Relevant Data
    if "df" not in st.session_state:
        st.error("DataFrame not found in session state.")
        st.stop()

    df = st.session_state["df"].copy()
    df.columns = df.columns.str.replace(" ", "-")
    df = df.drop_duplicates(subset=["symbol"])
    if "analyst_mean_target" in df.columns:
        df = df.drop(columns=["analyst_mean_target"])
    df["Div-Yield"] = pd.to_numeric(df["Div-Yield"], errors="coerce")
    df["Chowder-Number"] = pd.to_numeric(df["Chowder-Number"], errors="coerce")

    group1_df = df[(df["Div-Yield"] >= 3) & (df["Chowder-Number"] > custom_thresh_group1)]
    group2_df = df[(df["Div-Yield"] < 3) & (df["Chowder-Number"] > custom_thresh_group2)]

    # Combine results based on selection
    dfs = []
    if "Group 1" in selected_groups:
        dfs.append(group1_df)
    if "Group 2" in selected_groups:
        dfs.append(group2_df)

    if dfs:
        combined_df = pd.concat(dfs)
        combined_df = combined_df.drop_duplicates(subset=["symbol"])
        st.subheader("Chowder Numbers")
        combined_display = combined_df[[col for col in selected_columns if col in combined_df.columns]]
        try:
            gb = GridOptionsBuilder.from_dataframe(combined_display)
            gb.configure_default_column(**default_filter_params)
            gb.configure_side_bar(side_bar_config)
            for col in combined_display.columns:
                if col in tooltips:
                    gb.configure_column(col, headerTooltip=tooltips[col])
                else:
                    gb.configure_column(col)
            gridOptions = gb.build()
            AgGrid(combined_display, gridOptions=gridOptions,
                   enable_enterprise_modules=False, fit_columns_on_grid_load=True)
        except Exception as e:
            st.error(f"AgGrid display error: {e}")
            st.table(combined_display)
    else:
        st.write("No group selected.")
