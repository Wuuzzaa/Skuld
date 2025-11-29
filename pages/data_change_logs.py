import streamlit as st
import pandas as pd
import sqlite3
import os

# Datenbankpfad (wie im Docker-Compose gemountet)
DB_PATH = os.path.join(os.path.dirname(__file__), '../financial_data.db')

def get_data():
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM DataChangeLogs", conn)
        conn.close()
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
