import streamlit as st
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.page_display_dataframe import page_display_dataframe

# Titel
st.subheader("Symbol Page")

# get all symbols
if 'symbol_list' not in st.session_state:
    st.session_state.symbol_list = select_into_dataframe(query='select distinct symbol from "OptionDataMerged" ORDER BY symbol ASC')

# select one symbol with completion
selected_symbol = st.selectbox(
    "Select a Symbol:",
    options=st.session_state.symbol_list,
    index=None,  # Keine Vorselektion
    placeholder="Type to search... (e.g., MSFT, AAPL)",
)

params = {'symbol': selected_symbol}

# show fundamentals
st.subheader("Fundamental")
sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'symbolpage.sql'
df = select_into_dataframe(sql_file_path=sql_file_path, params=params)

page_display_dataframe(df, symbol_column='symbol')

# show iv history
st.subheader("IV History")
sql_file_path_iv = PATH_DATABASE_QUERY_FOLDER / 'iv_history_symbolpage.sql'
df_iv = select_into_dataframe(sql_file_path=sql_file_path_iv, params=params)

page_display_dataframe(df_iv, symbol_column='symbol')

# show technical indicators
st.subheader("Technical Indicators")
sql_file_path_technical_indicators = PATH_DATABASE_QUERY_FOLDER / 'technical_indicators_one_year_one_symbol.sql'
df_technical_indicators = select_into_dataframe(sql_file_path=sql_file_path_technical_indicators, params=params)

page_display_dataframe(df_technical_indicators, symbol_column='symbol')