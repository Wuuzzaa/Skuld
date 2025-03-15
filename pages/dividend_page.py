import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder

# Page Title and Subheader in main area
st.title("SKULD - Option Viewer")
st.subheader("Dividenden-Radar")

# -----------------------------------------------------------
# Detailed Explanation of the Chowder Number and its Calculation
st.markdown("""
### What Is the Chowder Number?

The **Chowder Number** is a screening metric popular in the dividend growth investing community.
It is typically calculated as the sum of a stock's **current dividend yield** and its **5-year average dividend yield**.
Here, the 5-year average dividend yield is used as a proxy for the dividend growth rate.

**Calculation:**  
Chowder Number = Dividend Yield + 5-Year Average Dividend Yield

**Rules of Thumb:**  
- For stocks with a **dividend yield of 3% or higher**, a Chowder Number above **14** is preferred.
- For stocks with a **dividend yield below 3%**, a Chowder Number above **15** is considered favorable.

This metric helps quickly identify dividend-paying stocks that may warrant further research.
""")
# -----------------------------------------------------------

# -------------------------
# Sidebar Controls (left side)
# -------------------------
st.sidebar.header("Filter Controls")

# Threshold sliders moved to the sidebar
thresh_high = st.sidebar.slider("Min Chowder Number (Div-Yield ≥ 3)", min_value=0, max_value=30, value=14, step=1)
thresh_low  = st.sidebar.slider("Min Chowder Number (Div-Yield < 3)", min_value=0, max_value=30, value=15, step=1)

# Button to calculate the Chowder Number
calc_button = st.sidebar.button("Calculate Chowder Number")

# Checkbox to apply the Chowder filter
apply_filter = st.sidebar.checkbox("Apply Chowder Filter", value=False)

# -------------------------
# DataFrame Handling
# -------------------------
# Load the DataFrame from session state
if "df" in st.session_state:
    df = st.session_state["df"]
else:
    st.error("DataFrame not found in session state.")
    st.stop()

# Clean column names: replace spaces with hyphens for consistency
df.columns = df.columns.str.replace(" ", "-")

# Calculate Chowder Number if the sidebar button is pressed
if calc_button:
    if "Div-Yield" in df.columns and "5Y-Avg-Yield" in df.columns:
        df["Chowder-Number"] = df["Div-Yield"] + df["5Y-Avg-Yield"]
        st.success("Chowder Number calculated and added to the DataFrame!")
        st.session_state["df"] = df
    else:
        st.error("Required columns 'Div-Yield' and '5Y-Avg-Yield' not found.")

# Apply filtering if checkbox is selected and Chowder-Number exists
if apply_filter and "Chowder-Number" in df.columns:
    condition = (
        ((df["Div-Yield"] >= 3) & (df["Chowder-Number"] > thresh_high)) |
        ((df["Div-Yield"] < 3) & (df["Chowder-Number"] > thresh_low))
    )
    df_display = df[condition]
else:
    df_display = df.copy()

# -------------------------
# AgGrid Configuration
# -------------------------
# Define tooltips for each column header (using cleaned names)
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
    "Chowder-Number": "Sum of Div-Yield and 5Y-Avg-Yield, a quick screening measure",
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

# Build AgGrid configuration
gb = GridOptionsBuilder.from_dataframe(df_display)
for col in df_display.columns:
    if col in column_tooltips:
        gb.configure_column(col, headerTooltip=column_tooltips[col])
    else:
        gb.configure_column(col)

# Configure conditional row coloring with enhanced logging
gb.configure_grid_options(getRowStyle=f"""
function(params) {{
    try {{
        console.log(new Date().toISOString(), "Row data:", params.data);
        var divYield = params.data["Div-Yield"];
        var chowderNumber = params.data["Chowder-Number"];
        console.log(new Date().toISOString(), "Div-Yield:", divYield, "Chowder-Number:", chowderNumber);
        if ((divYield >= 3 && chowderNumber > {thresh_high}) ||
            (divYield < 3 && chowderNumber > {thresh_low})) {{
            console.log(new Date().toISOString(), "Row passes filter. Coloring lightgreen.");
            return {{"background-color": "lightgreen"}};
        }} else {{
            console.log(new Date().toISOString(), "Row fails filter. Coloring #fdd.");
            return {{"background-color": "#fdd"}};
        }}
    }} catch(err) {{
        console.error(new Date().toISOString(), "Error in getRowStyle:", err);
        return {{"background-color": "#fff"}};
    }}
}}
""")
gridOptions = gb.build()

# -------------------------
# Display the DataFrame via AgGrid in the main area
# -------------------------
st.subheader("Total DataFrame")
if apply_filter:
    st.write("**Filtered DataFrame** (Chowder rules applied)")
else:
    st.write("**Original (unfiltered) DataFrame**")

AgGrid(df_display, gridOptions=gridOptions, enable_enterprise_modules=False, fit_columns_on_grid_load=True)
