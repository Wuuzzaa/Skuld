import streamlit as st

from src.database import select_into_dataframe

# Titel
st.subheader("Analyst Prices")

sql_query = """
    SELECT DISTINCT
        symbol,
        close,
        analyst_mean_target,
        recommendation,
        "Recommend.All",
        "target-close$",
        "target-close%"
    FROM
            OptionDataMerged;
"""

df = select_into_dataframe(query=sql_query)

# rename columns for the app-view
df = df.rename(
    columns={
        "symbol": "Symbol",
        "close": "Price",
        "analyst_mean_target": "Mean Analyst Target",
        "recommendation": "Indicators Recommendation",
        "Recommend.All": "Recommendation strength (-1 to 1)",
        "target-close$": "Difference ($) analyst target and price",
        "target-close%": "Difference (%) analyst target and price"
    }
)

st.dataframe(df, use_container_width=True)