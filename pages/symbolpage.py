import streamlit as st
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.page_display_dataframe import page_display_dataframe

# Titel
st.subheader("Symbol Page")

if 'symbol_list' not in st.session_state:
    st.session_state.symbol_list = select_into_dataframe(query='select distinct symbol from "OptionDataMerged" ORDER BY symbol ASC')

#print(st.session_state.symbol_list)

#symbol_input = st.text_input("Enter Symbol:", value="").upper()

selected_symbol = st.selectbox(
    "Select a Symbol:",
    options=st.session_state.symbol_list,
    index=None,  # Keine Vorselektion
    placeholder="Type to search... (e.g., MSFT, AAPL)",
)

params = {'symbol': selected_symbol}

sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'symbolpage.sql'
df = select_into_dataframe(sql_file_path=sql_file_path, params=params)

# show final dataframe
page_display_dataframe(df, symbol_column='symbol')