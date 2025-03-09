import pandas as pd
from config import *


def merge_data_dataframes():
    # Merge Option Data and Price/Indicator Data
    print("Merging Option Data and Price/Indicator Data")
    df_option_data = pd.read_feather(PATH_DATAFRAME_OPTION_DATA_FEATHER)
    df_price_indicators = pd.read_feather(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER)
    df_merged = pd.merge(df_option_data, df_price_indicators, how='left', on='symbol')

    # Join Yahoo Finance Analyst Price Targets
    print("Joining Yahoo Finance Analyst Price Targets")
    df_price_targets = pd.read_feather(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER)
    df_merged = pd.merge(df_merged, df_price_targets, how='left', on='symbol')

    # Join Dividend File Data
    print("Joining Dividend File Data")
    df_dividend_data = pd.read_feather(PATH_DIVIDEND_RADAR)
    df_merged = pd.merge(df_merged, df_dividend_data, how='left', left_on='symbol', right_on='Symbol')

    # Store merged DataFrame to file
    print(f"Storing merged DataFrame to: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
    df_merged[DATAFRAME_DATA_MERGED_COLUMNS].to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)