import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder

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

# Page Title and Subheader
st.subheader("Dividenden-Radar")

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

# DataFrame Handling: load the original DataFrame from session state
if "df" in st.session_state:
    df = st.session_state["df"].copy()  # work on a copy to avoid SettingWithCopyWarning
else:
    st.error("DataFrame not found in session state.")
    st.stop()

# Clean column names: replace spaces with hyphens
df.columns = df.columns.str.replace(" ", "-")

# (Optional) Drop an unwanted column, e.g., "analyst_mean_target", if present
if "analyst_mean_target" in df.columns:
    df = df.drop(columns=["analyst_mean_target"])

# Convert key columns to numeric
df["Div-Yield"] = pd.to_numeric(df["Div-Yield"], errors="coerce")
df["Chowder-Number"] = pd.to_numeric(df["Chowder-Number"], errors="coerce")

# Filter the DataFrame into two groups using the custom thresholds:
# Group 1: Div-Yield ≥ 3 and Chowder-Number > custom_thresh_group1
# Group 2: Div-Yield < 3 and Chowder-Number > custom_thresh_group2
group1_df = df[(df["Div-Yield"] >= 3) & (df["Chowder-Number"] > custom_thresh_group1)]
group2_df = df[(df["Div-Yield"] < 3) & (df["Chowder-Number"] > custom_thresh_group2)]

# Sidebar: Multi-select for columns to display.
# Default selection: only "symbol", "Div-Yield", and "Chowder-Number"
all_columns = df.columns.tolist()
default_columns = ["symbol", "Div-Yield", "Chowder-Number"]
selected_columns = st.sidebar.multiselect("Select columns to display", options=all_columns, default=default_columns)

if not selected_columns:
    st.error("Please select at least one column.")
    st.stop()

# For display, use the selected columns from the original filtered groups
group1_display = group1_df[selected_columns].drop_duplicates()
group2_display = group2_df[selected_columns].drop_duplicates()

tooltips = {"symbol": "Stock symbol"}

# Display Group 1 if toggled on
if st.session_state["show_group1"]:
    st.subheader(f"Group 1: Div-Yield ≥ 3 & Chowder Number > {custom_thresh_group1}")
    try:
        gb1 = GridOptionsBuilder.from_dataframe(group1_display)
        for col in group1_display.columns:
            if col in tooltips:
                gb1.configure_column(col, headerTooltip=tooltips[col])
            else:
                gb1.configure_column(col)
        gridOptions1 = gb1.build()
        AgGrid(group1_display, gridOptions=gridOptions1, enable_enterprise_modules=False, fit_columns_on_grid_load=True)
    except Exception as e:
        st.error(f"AgGrid display error in Group 1: {e}")
        st.table(group1_display)
else:
    st.write("Group 1 is hidden.")

# Display Group 2 if toggled on
if st.session_state["show_group2"]:
    st.subheader(f"Group 2: Div-Yield < 3 & Chowder Number > {custom_thresh_group2}")
    try:
        gb2 = GridOptionsBuilder.from_dataframe(group2_display)
        for col in group2_display.columns:
            if col in tooltips:
                gb2.configure_column(col, headerTooltip=tooltips[col])
            else:
                gb2.configure_column(col)
        gridOptions2 = gb2.build()
        AgGrid(group2_display, gridOptions=gridOptions2, enable_enterprise_modules=False, fit_columns_on_grid_load=True)
    except Exception as e:
        st.error(f"AgGrid display error in Group 2: {e}")
        st.table(group2_display)
else:
    st.write("Group 2 is hidden.")

if not st.session_state["show_group1"] and not st.session_state["show_group2"]:
    st.write("No group selected.")
