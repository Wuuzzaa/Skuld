import pandas as pd

from src.feature_engineering import feature_construction
from src.optiondata_csvs_to_df_merge import combine_csv_files
from src.tradingview_optionchain_scrapper import scrape_option_data
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.merge_csv_dataframes_data import merge_data_dataframes
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *

if __name__ == '__main__':
    print("#"*80)
    print("Get Yahoo Finance data")
    print("#" * 80)
    scrape_yahoo_finance_analyst_price_targets()
    print("Get Yahoo Finance data - Done")

    print("#" * 80)
    print("Get option data")
    print("#" * 80)
    for symbol in SYMBOLS:
        scrape_option_data(symbol=symbol, expiration_date=EXPIRATION_DATE, exchange=SYMBOLS_EXCHANGE[symbol], folderpath=PATH_OPTION_DATA_TRADINGVIEW)

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
    print("Feature engineering - Done")




