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

# Sidebar: toggle buttons for each group
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

# Sidebar: Multi-select for columns to display.
# Default selection now includes "Fair-Value" along with "symbol", "Div-Yield", and "Chowder-Number"
selected_columns = st.sidebar.multiselect(
    "Select columns to display", 
    options=["symbol", "Div-Yield", "Chowder-Number", "Fair-Value"],
    default=["symbol", "Div-Yield", "Chowder-Number", "Fair-Value"]
)

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

# For filtered (option strategy) display, load the DataFrame from session state.
if "df" in st.session_state:
    df = st.session_state["df"].copy()  # work on a copy to avoid SettingWithCopyWarning
else:
    st.error("DataFrame not found in session state.")
    st.stop()

# Clean column names for the filtered DataFrame: replace spaces with hyphens
df.columns = df.columns.str.replace(" ", "-")

# Remove duplicate entries based on the 'symbol' column
df = df.drop_duplicates(subset=["symbol"])

# (Optional) Drop an unwanted column, e.g., "analyst_mean_target", if present
if "analyst_mean_target" in df.columns:
    df = df.drop(columns=["analyst_mean_target"])

# Convert key columns to numeric
df["Div-Yield"] = pd.to_numeric(df["Div-Yield"], errors="coerce")
df["Chowder-Number"] = pd.to_numeric(df["Chowder-Number"], errors="coerce")

# Filter the DataFrame into two groups using the custom thresholds:
group1_df = df[(df["Div-Yield"] >= 3) & (df["Chowder-Number"] > custom_thresh_group1)]
group2_df = df[(df["Div-Yield"] < 3) & (df["Chowder-Number"] > custom_thresh_group2)]

# Display based on the chosen display mode
if display_option == "Show Full Dividend File":
    st.subheader("Full Dividend File")
    if os.path.exists(PATH_DIVIDEND_RADAR):
        try:
            full_dividend_df = pd.read_feather(PATH_DIVIDEND_RADAR)
            # Convert column names to lowercase and strip whitespace for matching
            full_dividend_df.columns = full_dividend_df.columns.str.lower().str.strip()
            # Lowercase and strip the selected columns for matching
            selected_cols_lower = [col.lower().strip() for col in selected_columns]
        except Exception as e:
            st.error(f"Error loading the full dividend file: {e}")
        else:
            # Only display the columns that are selected and exist in the file.
            display_columns = [col for col in selected_cols_lower if col in full_dividend_df.columns]
            # Ensure that "symbol" is included
            if "symbol" in full_dividend_df.columns and "symbol" not in display_columns:
                display_columns.insert(0, "symbol")
            if not display_columns:
                st.warning("None of the selected columns are available in the full dividend file. Displaying all columns instead.")
                full_display = full_dividend_df
            else:
                full_display = full_dividend_df[display_columns]
            try:
                gb_full = GridOptionsBuilder.from_dataframe(full_display)
                # Enable filtering and sorting by default for all columns
                gb_full.configure_default_column(filter=True, sortable=True)
                for col in full_display.columns:
                    if col in tooltips:
                        gb_full.configure_column(col, headerTooltip=tooltips[col])
                    else:
                        gb_full.configure_column(col)
                gridOptions_full = gb_full.build()
                AgGrid(full_display, gridOptions=gridOptions_full, 
                       enable_enterprise_modules=False, fit_columns_on_grid_load=True)
            except Exception as e:
                st.error(f"AgGrid display error for full dividend file: {e}")
                st.table(full_display)
    else:
        st.warning("Full dividend file not found. Please ensure the dividend data has been downloaded.")
else:
    # Show Only Option Strategy Relevant Data
    if st.session_state["show_group1"]:
        st.subheader(f"Group 1: Div-Yield ≥ 3 & Chowder Number > {custom_thresh_group1}")
        group1_display = group1_df[[col for col in selected_columns if col in group1_df.columns]]
        try:
            gb1 = GridOptionsBuilder.from_dataframe(group1_display)
            gb1.configure_default_column(filter=True, sortable=True)
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
            gb2.configure_default_column(filter=True, sortable=True)
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
