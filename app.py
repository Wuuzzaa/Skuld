import streamlit as st
import pandas as pd

from src.google_drive_downlod import load_updated_data,PATH_DATAFRAME_DATA_MERGED_CSV



# Seitenlayout und Titel festlegen
st.set_page_config(layout="wide")
st.title("SKULD - Option Viewer")

# CSV-Datei laden (wird heruntergeladen, falls nicht lokal vorhanden)
df = load_updated_data()
if df is None:
    st.error("Datei konnte nicht geladen werden. Bitte später erneut versuchen.")
    st.stop()  # Bricht die Ausführung der App ab

st.success(f"Datei erfolgreich geladen: {PATH_DATAFRAME_DATA_MERGED_CSV}")

# Beispiel: Darstellung des gesamten DataFrames in einem Tab
tab1, tab2, tab3 = st.tabs(["Gesamter DataFrame", "Gefilterte Ansicht", "Analyst Prices"])

with tab1:
    st.subheader("Gesamter DataFrame")
    st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Gefilterte Ansicht")
    # Filteroptionen – Beispiel für numerische Filter
    st.sidebar.header("Filter")
    filtered_df = df.copy()
    num_cols = df.select_dtypes(include=['float64', 'int64']).columns
    for col in num_cols:
        min_val, max_val = st.sidebar.slider(
            f"Filter für {col}",
            float(df[col].min()),
            float(df[col].max()),
            (float(df[col].min()), float(df[col].max()))
        )
        filtered_df = filtered_df[(filtered_df[col] >= min_val) & (filtered_df[col] <= max_val)]
    st.dataframe(filtered_df, use_container_width=True)

with tab3:
    st.subheader("Analyst Prices")
    df_tab3 = df[
        [
            "symbol",
            "close",
            "analyst_mean_target",
            "recommendation",
            "Recommend.All",
            "target-close$",
            "target-close%"
        ]
    ].drop_duplicates().reset_index(drop=True)
    # Spalten umbenennen für bessere Darstellung
    df_tab3 = df_tab3.rename(
        columns={
            "symbol": "Symbol",
            "close": "Price",
            "analyst_mean_target": "Mean Analyst Target",
            "recommendation": "Indicators Recommendation",
            "Recommend.All": "Recommendation strength (-1 to 1)",
            "target-close$": "Difference ($) analyst target and price",
            "target-close%": "Difference (%) analyst target and price"
        }
    )
    st.dataframe(df_tab3, use_container_width=True)
