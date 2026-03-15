import streamlit as st
import pandas as pd
import sqlite3
import os
from config import PATH_DATABASE_FILE
from src.database import select_into_dataframe

# Datenbankpfad (wie im Docker-Compose gemountet)


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
