import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder

# Page Title
st.title("SKULD - Option Viewer")

# Subheader
st.subheader("Dividenden-Radar")

# -----------------------------------------------------------
# Detailed Chowder Number Explanation
st.markdown("""
### What Is the Chowder Number?

The **Chowder Number** is a concept popularized in the dividend growth investing community. 
It is generally calculated as the sum of a stock's **current dividend yield** and its 
**dividend growth rate** (often the 5-year compound annual growth rate of the dividend). 
The logic behind this approach is that investors want not only a decent dividend yield 
but also evidence that the dividend is growing at a healthy pace.

Common *rules of thumb* for interpreting the Chowder Number:
- If a stock's **dividend yield is 3% or higher**, many investors look for a Chowder Number **above 14**.
- If a stock's **dividend yield is below 3%**, they often look for a Chowder Number **above 15**.

This is not a hard-and-fast rule but rather a quick screening method to see whether a 
dividend-paying stock might warrant further research. In this app, you can adjust the 
thresholds for these rules below, then apply the filter to see which stocks meet your 
chosen criteria.
""")
# -----------------------------------------------------------

# Sliders for dynamic Chowder thresholds
thresh_high = st.slider(
    "Minimum Chowder Number for stocks with Div-Yield >= 3",
    min_value=0, max_value=30, value=14, step=1
)
thresh_low = st.slider(
    "Minimum Chowder Number for stocks with Div-Yield < 3",
    min_value=0, max_value=30, value=15, step=1
)

# Toggle button for applying the Chowder filter
if "chowder_filter_on" not in st.session_state:
    st.session_state["chowder_filter_on"] = False

if st.button("Toggle Chowder Filter"):
    st.session_state["chowder_filter_on"] = not st.session_state["chowder_filter_on"]

# Load the DataFrame from session state
df = st.session_state["df"]

# Replace all spaces in column names with hyphens
df.columns = df.columns.str.replace(" ", "-")

# Apply filtering if toggle is active
if st.session_state["chowder_filter_on"]:
    condition = (
        ((df["Div-Yield"] >= 3) & (df["Chowder-Number"] > thresh_high)) |
        ((df["Div-Yield"] < 3) & (df["Chowder-Number"] > thresh_low))
    )
    df_display = df[condition]
else:
    df_display = df.copy()

# Define tooltips for each column header (matching hyphenated names)
column_tooltips = {
    "Company": "Name of the company",
    "FV": "Fair value of the stock",
    "Sector": "Sector in which the company operates",
    "No-Years": "Number of years included in analysis",
    "Price": "Current stock price",
    "Div-Yield": "Dividend yield percentage",
    "5Y-Avg-Yield": "5-year average dividend yield percentage",
    "Current-Div": "Current dividend payment amount",
    "Annualized": "Annualized dividend rate",
    "Previous-Div": "Previous dividend payment",
    "Ex-Date": "Ex-dividend date",
    "Pay-Date": "Dividend payment date",
    "Low": "Lowest stock price in the period",
    "High": "Highest stock price in the period",
    "DGR-1Y": "Dividend growth rate over 1 year",
    "DGR-3Y": "Dividend growth rate over 3 years",
    "DGR-5Y": "Dividend growth rate over 5 years",
    "DGR-10Y": "Dividend growth rate over 10 years",
    "TTR-1Y": "Total return over 1 year",
    "TTR-3Y": "Total return over 3 years",
    "Fair-Value": "Calculated fair value of the stock",
    "FV-%": "Percentage difference from fair value",
    "Streak-Basis": "Basis for calculating dividend streaks",
    "Chowder-Number": "Combines dividend yield with the dividend growth rate",
    "EPS-1Y": "Earnings per share for the past year",
    "Revenue-1Y": "Revenue over the past year",
    "NPM": "Net profit margin",
    "CF/Share": "Cash flow per share",
    "ROE": "Return on equity",
    "Current-R": "Current ratio of the company",
    "Debt/Capital": "Debt-to-capital ratio",
    "ROTC": "Return on total capital",
    "P/E": "Price-to-earnings ratio",
    "P/BV": "Price-to-book value ratio",
    "PEG": "Price/earnings to growth ratio",
    "Industry": "Industry in which the company operates"
}

# Build grid options for AgGrid
gb = GridOptionsBuilder.from_dataframe(df_display)

# Configure column tooltips
for col in df_display.columns:
    if col in column_tooltips:
        gb.configure_column(col, headerTooltip=column_tooltips[col])
    else:
        gb.configure_column(col)

# Conditional row coloring based on Chowder criteria
gb.configure_grid_options(getRowStyle=f"""
function(params) {{
    if ((params.data["Div-Yield"] >= 3 && params.data["Chowder-Number"] > {thresh_high}) ||
        (params.data["Div-Yield"] < 3 && params.data["Chowder-Number"] > {thresh_low})) {{
        return {{'background-color': 'lightgreen'}};
    }} else {{
        return {{'background-color': '#fdd'}};
    }}
}}
""")

gridOptions = gb.build()

# Subheader for the displayed DataFrame
st.subheader("Total DataFrame")
if st.session_state["chowder_filter_on"]:
    st.write("**Filtered DataFrame** (Chowder rules applied)")
else:
    st.write("**Original (unfiltered) DataFrame**")

# Display the interactive grid
AgGrid(df_display, gridOptions=gridOptions, enable_enterprise_modules=False, fit_columns_on_grid_load=True)
