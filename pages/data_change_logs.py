import logging

import streamlit as st
import pandas as pd
import sqlite3
import os
from src.database import select_into_dataframe
from src.decorator_log_function import log_function

logger = logging.getLogger(__name__)

@log_function
def get_data():
    try:
        df = select_into_dataframe('SELECT * FROM "DataChangeLogs"')
        return df
    except Exception as e:
        st.error(f"Fehler beim Laden der Daten: {e}")
        return pd.DataFrame()

st.subheader("DataChangeLogs Übersicht")

with st.spinner("Lade DataChangeLogs..."):
    df = get_data()

if not df.empty:
    st.dataframe(df)
else:
    st.info("Keine Daten in DataChangeLogs vorhanden.")
