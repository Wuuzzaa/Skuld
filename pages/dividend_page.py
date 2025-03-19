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

# Sidebar: toggle buttons for each group (used in option strategy mode)
if "show_group1" not in st.session_state:
    st.session_state["show_group1"] = True
if "show_group2" not in st.session_state:
    st.session_state["show_group2"] = True

if st.sidebar.button("Toggle Group 1"):
    st.session_state["show_group1"] = not st.session_state["show_group1"]
if st.sidebar.button("Toggle Group 2"):
    st.session_state["show_group2"] = not st.session_state["show_group2"]

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
            # Normalize column names: lower-case and strip whitespace
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

# Set default columns. For full dividend file, we expect lower-case names.
default_options = [col.lower() for col in ["symbol", "Div-Yield", "Chowder-Number", "Fair-Value"]]
default_columns = [col for col in available_columns if col in default_options]

selected_columns = st.sidebar.multiselect("Select columns to display", options=available_columns, default=default_columns)
if not selected_columns:
    st.error("Please select at least one column.")
    st.stop()

# Define a dictionary for tooltips (if needed)
tooltips = {"symbol": "Stock symbol"}

# Page Title and Subheader
st.title("SKULD - Option Viewer")
st.subheader("Dividend Radar")

st.markdown("""
### What Is the Chowder Number?

The **Chowder Number** is a screening metric popular in the dividend growth investing community.
It is typically calculated as the sum of a stock's **current dividend yield** and its **5-year average dividend yield**.
Here, the 5-year average dividend yield is used as a proxy for the dividend growth rate.

**Rules of Thumb:**  
- **Group 1:** For stocks with a dividend yield of **3% or higher**, a Chowder Number above the configured threshold 14 is preferred.  
- **Group 2:** For stocks with a dividend yield **below 3%**, a Chowder Number above the configured threshold 15 is considered favorable.

This metric helps quickly identify dividend-paying stocks that may warrant further research.
""")

# Define side bar configuration for AgGrid (to show the columns tool panel)
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

# Define default filter parameters for AgGrid columns (with floating filters enabled)
default_filter_params = {
    'filter': True,
    'sortable': True,
    'resizable': True,
    'floatingFilter': True,
    'filterParams': {
        'filterOptions': ['contains', 'notContains', 'equals', 'notEqual', 'startsWith', 'endsWith']
    }
}

# Display logic based on the selected display mode
if display_option == "Show Full Dividend File":
    st.subheader("Full Dividend File")
    if os.path.exists(PATH_DIVIDEND_RADAR):
        try:
            full_dividend_df = pd.read_feather(PATH_DIVIDEND_RADAR)
            # Normalize columns: lower-case and strip whitespace
            full_dividend_df.columns = full_dividend_df.columns.str.lower().str.strip()
            # Use only the selected columns that exist in the file; ensure "symbol" is included.
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
    # Clean column names: replace spaces with hyphens
    df.columns = df.columns.str.replace(" ", "-")
    df = df.drop_duplicates(subset=["symbol"])
    if "analyst_mean_target" in df.columns:
        df = df.drop(columns=["analyst_mean_target"])
    df["Div-Yield"] = pd.to_numeric(df["Div-Yield"], errors="coerce")
    df["Chowder-Number"] = pd.to_numeric(df["Chowder-Number"], errors="coerce")
    group1_df = df[(df["Div-Yield"] >= 3) & (df["Chowder-Number"] > custom_thresh_group1)]
    group2_df = df[(df["Div-Yield"] < 3) & (df["Chowder-Number"] > custom_thresh_group2)]
    
    if st.session_state["show_group1"]:
        st.subheader(f"Group 1: Div-Yield ≥ 3 & Chowder Number > {custom_thresh_group1}")
        group1_display = group1_df[[col for col in selected_columns if col in group1_df.columns]]
        try:
            gb1 = GridOptionsBuilder.from_dataframe(group1_display)
            gb1.configure_default_column(**default_filter_params)
            gb1.configure_side_bar(side_bar_config)
            for col in group1_display.columns:
                if col in tooltips:
                    gb1.configure_column(col, headerTooltip=tooltips[col])
                else:
                    gb1.configure_column(col)
            gridOptions1 = gb1.build()
            AgGrid(group1_display, gridOptions=gridOptions1, 
                   enable_enterprise_modules=False, fit_columns_on_grid_load=True)
        except Exception as e:
            st.error(f"AgGrid display error in Group 1: {e}")
            st.table(group1_display)
    else:
        st.write("Group 1 is hidden.")
    
    if st.session_state["show_group2"]:
        st.subheader(f"Group 2: Div-Yield < 3 & Chowder Number > {custom_thresh_group2}")
        group2_display = group2_df[[col for col in selected_columns if col in group2_df.columns]]
        try:
            gb2 = GridOptionsBuilder.from_dataframe(group2_display)
            gb2.configure_default_column(**default_filter_params)
            gb2.configure_side_bar(side_bar_config)
            for col in group2_display.columns:
                if col in tooltips:
                    gb2.configure_column(col, headerTooltip=tooltips[col])
                else:
                    gb2.configure_column(col)
            gridOptions2 = gb2.build()
            AgGrid(group2_display, gridOptions=gridOptions2, 
                   enable_enterprise_modules=False, fit_columns_on_grid_load=True)
        except Exception as e:
            st.error(f"AgGrid display error in Group 2: {e}")
            st.table(group2_display)
    else:
        st.write("Group 2 is hidden.")
    
    if not st.session_state["show_group1"] and not st.session_state["show_group2"]:
        st.write("No group selected.")
