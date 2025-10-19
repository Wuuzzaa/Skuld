import streamlit as st
from src.page_display_dataframe import page_display_dataframe

# Titel
st.subheader("Multifactor Swingtrading")

df = calculate_multifactor_swingtrading_strategy()

# show final dataframe
page_display_dataframe(df, symbol_column='symbol')