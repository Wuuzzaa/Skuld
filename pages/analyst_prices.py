import streamlit as st
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.page_display_dataframe import page_display_dataframe
from src.streamlit_helpers import render_date_filter

# Titel
st.subheader("Analyst Prices")

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'analyst_prices.sql'
df = select_timetravel_into_dataframe(date = selected_date, sql_file_path=sql_file_path)

# rename columns for the app-view
df = df.rename(
    columns={
        #"symbol": "Symbol", # let it lowercase
        "close": "Price",
        "analyst_mean_target": "Mean Analyst Target",
        #"recommendation": "Indicators Recommendation",
        #"Recommend.All": "Recommendation strength (-1 to 1)",
        "target-close$": "Difference ($) analyst target and price",
        "target-close%": "Difference (%) analyst target and price"
    }
)

# show final dataframe
page_display_dataframe(df, symbol_column='symbol')