import streamlit as st
import pandas as pd
from config import *


# Layout
st.set_page_config(layout="wide")

# Titel
st.title("SKULD - Option Viewer")

# load dataframe
df = pd.read_csv(PATH_DATAFRAME_DATA_MERGED_CSV)
st.success(f"Datei erfolgreich geladen: {PATH_DATAFRAME_DATA_MERGED_CSV}")

# add tabs
tab1, tab2, tab3 = st.tabs(
    [
        "Gesamter DataFrame",
        "Gefilterte Ansicht",
        "Analyst Prices"
    ]
)

with tab1:
    st.subheader("Gesamter DataFrame")
    #st.write(df)
    st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Gefilterte Ansicht")

    # Filteroptionen bereitstellen
    st.sidebar.header("Filter")

    # Filter für numerische Spalten
    num_cols = df.select_dtypes(include=['float64', 'int64']).columns
    filtered_df = df.copy()
    for col in num_cols:
        min_val, max_val = st.sidebar.slider(
            f"Filter für {col}",
            float(df[col].min()),
            float(df[col].max()),
            (float(df[col].min()), float(df[col].max())),
        )
        filtered_df = filtered_df[(filtered_df[col] >= min_val) & (filtered_df[col] <= max_val)]

    # Filter für kategorische Spalten
    cat_cols = df.select_dtypes(include=['object']).columns
    for col in cat_cols:
        selected = st.sidebar.multiselect(f"Werte für {col} auswählen", df[col].unique())
        if selected:
            filtered_df = filtered_df[filtered_df[col].isin(selected)]

    # Gefilterter DataFrame anzeigen
    #st.write(filtered_df)
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

    # rename columns for the app-view
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

    #st.write(df_tab3)
    st.dataframe(df_tab3, use_container_width=True)






