import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder

# Page Title and Subheader
st.title("SKULD - Option Viewer")
st.subheader("Dividenden-Radar")

# -----------------------------------------------------------
# Detailed Chowder Number Explanation
st.markdown("""
### What Is the Chowder Number?

The **Chowder Number** is a concept popularized in the dividend growth investing community. 
It is typically calculated as the sum of a stock's **current dividend yield** and its 
**5-year average dividend yield** (used here as a proxy for the dividend growth rate). 
The idea behind this calculation is that a high Chowder Number not only reflects a good yield 
but also suggests the potential for future dividend increases.

Rules of thumb:
- For stocks with a **dividend yield of 3% or higher**, a Chowder Number above **14** is preferred.
- For stocks with a **dividend yield below 3%**, a Chowder Number above **15** is considered favorable.

This metric serves as a quick screening tool to identify dividend-paying stocks that may warrant further research.
""")
# -----------------------------------------------------------

# Create a mock DataFrame with some example data
data = {
    "Company": ["A", "B", "C", "D"],
    "Div Yield": [2.5, 3.2, 4.1, 2.8],
    "5Y Avg Yield": [1.0, 2.0, 1.5, 2.5],
    "Price": [100, 150, 200, 120],
    "Sector": ["Tech", "Finance", "Health", "Utilities"]
}
df = pd.DataFrame(data)

# Replace spaces in column names with hyphens for consistency
df.columns = df.columns.str.replace(" ", "-")

# Button to calculate the Chowder Number
if st.button("Calculate Chowder Number"):
    # Calculate Chowder-Number as the sum of Div-Yield and 5Y-Avg-Yield
    # (This is a common approximation; you may adjust the formula if needed.)
    df["Chowder-Number"] = df["Div-Yield"] + df["5Y-Avg-Yield"]
    st.success("Chowder Number calculated and added to the DataFrame!")

# Toggle button for applying a fixed filter
if "chowder_filter_on" not in st.session_state:
    st.session_state["chowder_filter_on"] = False

if st.button("Toggle Chowder Filter"):
    st.session_state["chowder_filter_on"] = not st.session_state["chowder_filter_on"]

# Fixed thresholds for filtering
thresh_high = 14
thresh_low = 15

# Apply filtering only if the Chowder-Number column exists
if "Chowder-Number" in df.columns:
    if st.session_state["chowder_filter_on"]:
        condition = (
            ((df["Div-Yield"] >= 3) & (df["Chowder-Number"] > thresh_high)) |
            ((df["Div-Yield"] < 3) & (df["Chowder-Number"] > thresh_low))
        )
        df_display = df[condition]
    else:
        df_display = df.copy()
else:
    df_display = df.copy()

# Build AgGrid configuration with conditional row coloring
gb = GridOptionsBuilder.from_dataframe(df_display)
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

st.subheader("Total DataFrame")
if st.session_state["chowder_filter_on"]:
    st.write("**Filtered DataFrame** (Chowder rules applied)")
else:
    st.write("**Original (unfiltered) DataFrame**")

AgGrid(df_display, gridOptions=gridOptions, enable_enterprise_modules=False, fit_columns_on_grid_load=True)
