import streamlit as st
from config import *
from src.page_display_dataframe import page_display_dataframe
from src.database import select_into_dataframe
from src.strategy_atlas_multi_signal_alpha import calculate_atlas_multi_signal_alpha_strategy

# Titel
st.subheader("Atlas Multi Signal Alpha")

# SQL query
sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'atlas_multi_signal_alpha.sql'

df = select_into_dataframe(sql_file_path=sql_file_path)
df = calculate_atlas_multi_signal_alpha_strategy(df=df)

# Display dataframe
page_display_dataframe(df, symbol_column='symbol')