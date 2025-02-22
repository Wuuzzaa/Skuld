import pandas as pd
from config import *


def merge_data_dataframes():
    print("Merge Option and Price Indicators Data")
    df_option_data = pd.read_csv(PATH_DATAFRAME_OPTION_DATA_CSV)
    df_price_indicators = pd.read_csv(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_CSV)
    df_merged = pd.merge(df_option_data, df_price_indicators, how='left', left_on='symbol', right_on='symbol')

    print("Join Yahoo Finance Analyst Price targets")
    df_price_targets = pd.read_csv(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_CSV)
    df_merged = pd.merge(df_merged, df_price_targets, how='left', left_on='symbol', right_on='symbol')

    print(f"Store merged to: {PATH_DATAFRAME_DATA_MERGED_CSV}")
    df_merged[DATAFRAME_DATA_MERGED_COLUMNS].to_csv(PATH_DATAFRAME_DATA_MERGED_CSV, index=False)