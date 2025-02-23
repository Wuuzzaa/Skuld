import streamlit as st

# Titel
st.subheader("Analyst Prices")


df = st.session_state['df']

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

# rename columns for the app-view
df_tab3 = df_tab3.rename(
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

st.dataframe(df_tab3, use_container_width=True)