import streamlit as st
import pandas as pd
from config import *

# streamlit run C:\Users\jonas\PycharmProjects\Skuld\app.py


from src.feature_engineering import feature_construction, type_casting
from src.optiondata_csvs_to_df_merge import combine_csv_files
from src.tradingview_optionchain_scrapper import scrape_option_data
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.merge_csv_dataframes_data import merge_data_dataframes
from src.util import create_all_project_folders, get_option_expiry_dates
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *


create_all_project_folders()

print("#"*80)
print("Get Yahoo Finance data")
print("#" * 80)
scrape_yahoo_finance_analyst_price_targets()
print("Get Yahoo Finance data - Done")

print("#" * 80)
print("Get option data")
print("#" * 80)
for expiration_date in get_option_expiry_dates():
    for symbol in SYMBOLS:
        scrape_option_data(symbol=symbol, expiration_date=expiration_date, exchange=SYMBOLS_EXCHANGE[symbol], folderpath=PATH_OPTION_DATA_TRADINGVIEW)

print("Get option data - Done")
print("#" * 80)
print("Combine option data JSON to csv")
print("#" * 80)
df = combine_csv_files(folder_path=PATH_OPTION_DATA_TRADINGVIEW, data_csv_path=PATH_DATAFRAME_OPTION_DATA_CSV)
print("Combine option data JSON to csv - Done")

print("#" * 80)
print("Get price and technical indicators")
print("#" * 80)
scrape_and_save_price_and_technical_indicators(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_CSV)
print("Get price and technical indicators - Done")

print("#" * 80)
print("Merge all csv dataframe files")
print("#" * 80)
merge_data_dataframes()
print("Merge all csv dataframe files - Done")

print("#" * 80)
print("Feature engineering")
print("#" * 80)
feature_construction()
type_casting()
print("Feature engineering - Done")


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






