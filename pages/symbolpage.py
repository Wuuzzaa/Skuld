import streamlit as st
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.page_display_dataframe import page_display_dataframe
from src.streamlit_helpers import render_date_filter, render_symbol_filter

# Titel
st.subheader("Symbol Page")

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)
selected_symbol = render_symbol_filter(
    symbol_query='select distinct symbol from "OptionDataMerged" ORDER BY symbol ASC',
)

if selected_symbol is None:
    st.warning("Please select a symbol to display the symbol page content.")
    st.stop()

params = {'symbol': selected_symbol}

# show fundamentals
st.subheader("Fundamental")
sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'symbolpage.sql'
df = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path, params=params)

page_display_dataframe(df, symbol_column='symbol')

# show iv history
st.subheader("IV History")
sql_file_path_iv = PATH_DATABASE_QUERY_FOLDER / 'iv_history_symbolpage.sql'
df_iv = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path_iv, params=params)

page_display_dataframe(df_iv, symbol_column='symbol')

# show technical indicators
st.subheader("Technical Indicators")
sql_file_path_technical_indicators = PATH_DATABASE_QUERY_FOLDER / 'technical_indicators_one_year_one_symbol.sql'
df_technical_indicators = select_timetravel_into_dataframe(date=selected_date, sql_file_path=sql_file_path_technical_indicators, params=params)

page_display_dataframe(df_technical_indicators, symbol_column='symbol')

if selected_symbol == 'INTC':
    st.subheader("Hourly Option History for INTC")
    df_intc = select_into_dataframe('SELECT * FROM "OptionDataMassiveHistoryHourly" WHERE symbol = \'INTC\' AND timestamp >= CURRENT_DATE - INTERVAL \'1 days\' ORDER BY option_osi, timestamp DESC')

    # page_display_dataframe(df_intc, symbol_column='symbol')

    csv_data = df_intc.to_csv(index=False)
    st.download_button(
        label=f"⬇️ Option Data History ({len(df_intc)} Options) as CSV",
        data=csv_data,
        file_name=f"option_data_history_INTC.csv",
        mime="text/csv",
    )