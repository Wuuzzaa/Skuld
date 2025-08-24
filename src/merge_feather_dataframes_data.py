import pandas as pd
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    print("Dividend columns:", df_dividend_data.columns.tolist())
    print("Has Classification?", 'Classification' in df_dividend_data.columns)
    df_merged = pd.merge(df_merged, df_dividend_data, how='left', left_on='symbol', right_on='Symbol')

    # Join Earning Dates
    print("Joining Earning Dates")
    df_earning_dates = pd.read_feather(PATH_DATAFRAME_EARNING_DATES_FEATHER)
    df_merged = pd.merge(df_merged, df_earning_dates, how='left', left_on='symbol', right_on='symbol')

    # Join Yahoo Option Chain
    print("Joining Yahoo Option Chain")
    df_yahooquery_option_chain = pd.read_feather(PATH_DATAFRAME_YAHOOQUERY_OPTION_CHAIN_FEATHER, columns=['contractSymbol', 'option_volume', 'option_open_interest'])
    df_merged = pd.merge(df_merged, df_yahooquery_option_chain, how='left', left_on='option_osi', right_on='contractSymbol')

    # todo yahoo query financials mergen

    # Store merged DataFrame to file
    print(f"Storing merged DataFrame to: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
    df_merged[DATAFRAME_DATA_MERGED_COLUMNS].to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)



if __name__ == '__main__':
    import time

    start = time.time()
    merge_data_dataframes()
    end = time.time()
    duration = end - start

    print(f"\nDurchlaufzeit: {duration:.4f} Sekunden") 