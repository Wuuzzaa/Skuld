import streamlit as st
from config import *
from src.multifactor_swingtrading_strategy import calculate_multifactor_swingtrading_strategy
from src.page_display_dataframe import page_display_dataframe
from src.database import select_into_dataframe

# Titel
st.subheader("Multifactor Swingtrading")

# sql query
sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'multifactor_swingtrading.sql'
df = select_into_dataframe(sql_file_path=sql_file_path)

# calculate strategy
df = calculate_multifactor_swingtrading_strategy(df)

# show final dataframe
page_display_dataframe(df, symbol_column='symbol')