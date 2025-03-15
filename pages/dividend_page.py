import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder

# Page Title
st.subheader("Dividenden-Radar")

# Simple explanation of the Chowder Number and other columns
st.markdown("""
**Chowder Number Explanation:**

The Chowder Number is a custom metric used to assess the attractiveness of a stock's dividend by combining dividend yield with other financial factors.  
Hover over any column header to see a brief explanation of that column.
""")

# Dynamic threshold sliders for Chowder filtering
thresh_high = st.slider("Minimum Chowder Number for stocks with Div Yield >= 3", min_value=0, max_value=30, value=14, step=1)
thresh_low = st.slider("Minimum Chowder Number for stocks with Div Yield < 3", min_value=0, max_value=30, value=15, step=1)

# Toggle button for applying the Chowder filter
if "chowder_filter_on" not in st.session_state:
    st.session_state["chowder_filter_on"] = False
if st.button("Toggle Chowder Filter"):
    st.session_state["chowder_filter_on"] = not st.session_state["chowder_filter_on"]

# Load the example DataFrame from session state
df = st.session_state["df"]

# Apply filtering if toggle is active, otherwise use the original DataFrame
if st.session_state["chowder_filter_on"]:
    condition = (
        ((df["Div Yield"] >= 3) & (df["Chowder Number"] > thresh_high)) |
        ((df["Div Yield"] < 3) & (df["Chowder Number"] > thresh_low))
    )
    df_display = df[condition]
else:
    df_display = df.copy()

# Define tooltips for each column header
column_tooltips = {
    "Company": "Name of the company",
    "FV": "Fair value of the stock",
    "Sector": "Sector in which the company operates",
    "No Years": "Number of years included in analysis",
    "Price": "Current stock price",
    "Div Yield": "Dividend yield percentage",
    "5Y Avg Yield": "5-year average dividend yield percentage",
    "Current Div": "Current dividend payment amount",
    "Annualized": "Annualized dividend rate",
    "Previous Div": "Previous dividend payment",
    "Ex-Date": "Ex-dividend date",
    "Pay-Date": "Dividend payment date",
    "Low": "Lowest stock price in the period",
    "High": "Highest stock price in the period",
    "DGR 1Y": "Dividend growth rate over 1 year",
    "DGR 3Y": "Dividend growth rate over 3 years",
    "DGR 5Y": "Dividend growth rate over 5 years",
    "DGR 10Y": "Dividend growth rate over 10 years",
    "TTR 1Y": "Total return over 1 year",
    "TTR 3Y": "Total return over 3 years",
    "Fair Value": "Calculated fair value of the stock",
    "FV %": "Percentage difference from fair value",
    "Streak Basis": "Basis for calculating dividend streaks",
    "Chowder Number": "Custom metric combining dividend yield with financial factors",
    "EPS 1Y": "Earnings per share for the past year",
    "Revenue 1Y": "Revenue over the past year",
    "NPM": "Net profit margin",
    "CF/Share": "Cash flow per share",
    "ROE": "Return on equity",
    "Current R": "Current ratio of the company",
    "Debt/Capital": "Debt-to-capital ratio",
    "ROTC": "Return on total capital",
    "P/E": "Price-to-earnings ratio",
    "P/BV": "Price-to-book value ratio",
    "PEG": "Price/earnings to growth ratio",
    "Industry": "Industry in which the company operates"
}

# Build grid options for AgGrid with tooltips for each column header
gb = GridOptionsBuilder.from_dataframe(df_display)
for col in df_display.columns:
    if col in column_tooltips:
        gb.configure_column(col, headerTooltip=column_tooltips[col])
    else:
        gb.configure_column(col)

# Add conditional row coloring based on the Chowder criteria using JavaScript getRowStyle
# Rows meeting the criteria will be colored light green, others in light red.
gb.configure_grid_options(getRowStyle=f"""
function(params) {{
    if ((params.data["Div Yield"] >= 3 && params.data["Chowder Number"] > {thresh_high}) ||
        (params.data["Div Yield"] < 3 && params.data["Chowder Number"] > {thresh_low})) {{
        return {{'background-color': 'lightgreen'}};
    }} else {{
        return {{'background-color': '#fdd'}};
    }}
}}
""")

gridOptions = gb.build()

st.subheader("Total DataFrame")
if st.session_state["chowder_filter_on"]:
    st.write("**Filtered DataFrame** (Chowder rules applied)")
else:
    st.write("**Original (unfiltered) DataFrame**")

# Display the interactive grid with tooltips and row coloring enabled
AgGrid(df_display, gridOptions=gridOptions, enable_enterprise_modules=False, fit_columns_on_grid_load=True)
