import argparse
from src.database import run_migrations, select_into_dataframe, truncate_table
from src.feature_engineering import feature_construction
from src.tradingview_optionchain_scrapper import scrape_option_data_trading_view
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.merge_feather_dataframes_data import merge_data_dataframes
from src.util import create_all_project_folders, clean_temporary_files, clean_all_data_files
from src.yahooquery_earning_dates import scrape_earning_dates, scrape_earning_dates2
from src.yahooquery_option_chain import get_yahooquery_option_chain, get_yahooquery_option_chain2
from src.yahooquery_financials import generate_fundamental_data, generate_fundamental_data2
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets, scrape_yahoo_finance_analyst_price_targets2, scrape_yahoo_finance_analyst_price_targets3
from config import *
from src.google_drive_upload import upload_merged_data, upload_database
from src.dividend_radar import process_dividend_data
from config_utils import get_filtered_symbols_and_dates_with_logging
from config_utils import generate_expiry_dates_from_rules
import pandas as pd
import time


def main(upload_google_drive=True):
    start_main = time.time()
    run_migrations()
    print("#" * 80)
    print(f"Starting Data Collection Pipeline")

    print(f"Symbol selection mode: {SYMBOL_SELECTION['mode']}")

    # Show configuration summary
    enabled_rules = [rule for rule in OPTIONS_COLLECTION_RULES if rule.get("enabled", False)]
    print(f"[INFO] Enabled collection rules: {len(enabled_rules)}")
    for rule in enabled_rules:
        print(f"  - {rule['name']}: {rule['days_range']} days, {rule['frequency']}")

    if SYMBOL_SELECTION.get("use_max_limit", False) and "max_symbols" in SYMBOL_SELECTION:
        print(f"[INFO] Symbol limit: {SYMBOL_SELECTION['max_symbols']}")

    print(f"upload_df_google_drive: {upload_google_drive}\n")
    print("#" * 80)

    # CLEAN temporary files from previous runs
    # Use clean_all_data_files() for complete cleanup, clean_temporary_files() for normal cleanup
    clean_temporary_files()  # Change to clean_all_data_files() if you want complete cleanup

    create_all_project_folders()

    print("#"*80)
    print("Get Yahoo Finance data - Analyst Price Targets")
    start = time.time()
    print("#" * 80)
    scrape_yahoo_finance_analyst_price_targets3()
    print(f"Get Yahoo Finance data - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Get option data")
    print("#" * 80)

    # NEW: Centralized config-driven data collection
    # Get expiry dates as strings in YYYY-MM-DD format for filtering
    expiry_date_strings = generate_expiry_dates_from_rules()
    symbols_to_use, filtered_expiry_dates = get_filtered_symbols_and_dates_with_logging(
        expiry_date_strings, "Option Data Collection"
    )

    # Convert filtered dates back to integers for scraping functions
    # expiry_dates_int = [int(date_str.replace("-", "")) for date_str in filtered_expiry_dates]

    # print(f"Collecting data from Trading View for {len(symbols_to_use)} symbols and {len(expiry_dates_int)} expiry dates")
    print(f"Collecting data from Trading View for {len(symbols_to_use)} symbols and all expiration dates")

    start = time.time()
    scrape_option_data_trading_view(symbols_to_use)

    print(f"Get option data from Trading View - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Get price and technical indicators")
    start = time.time()
    print("#" * 80)
    scrape_and_save_price_and_technical_indicators()
    print(f"Get price and technical indicators - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Dividend Radar")
    start = time.time()
    print("#" * 80)
    process_dividend_data(path_outputfile=PATH_DIVIDEND_RADAR)
    # Debug: Check if Classification exists in dividend data
    df_div = pd.read_feather(PATH_DIVIDEND_RADAR)
    print("Dividend Radar columns:", df_div.columns.tolist())
    print("Has Classification?", 'Classification' in df_div.columns)
    if 'Classification' in df_div.columns:
        print("Classification values:", df_div['Classification'].value_counts())
    print(f"Dividend Radar - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Earning Dates")
    start = time.time()
    print("#" * 80)
    scrape_earning_dates2()
    print(f"Earning Dates - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Yahoo Query Option Chain")
    start = time.time()
    print("#" * 80)
    get_yahooquery_option_chain2()
    print(f"Yahoo Query Option Chain - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Yahoo Query Fundamentals")
    start = time.time()
    print("#" * 80)
    generate_fundamental_data2()
    print(f"Yahoo Query Fundamentals - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Merge all feather dataframe files (with live prices)")
    start = time.time()
    print("#" * 80)
    merge_data_dataframes()
    # Debug: Check merged data
    df_merged = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    print("Final columns:", len(df_merged.columns.tolist()))
    print("Has Classification?", 'Classification' in df_merged.columns)
    print(f"Merge all feather dataframe files - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Feature engineering")
    start = time.time()
    print("#" * 80)
    feature_construction()
    print(f"Feature engineering - Done - Runtime: {int(time.time() - start)}s")

    if upload_google_drive:
        print("#" * 80)
        print("Upload database to Google Drive")
        start = time.time()
        print("#" * 80)
        upload_database()
        print(f"Upload database to Google Drive - Done - Runtime: {int(time.time() - start)}s")
        
        print("#" * 80)
        print("Upload merged dataframe file to Google Drive")
        start = time.time()
        print("#" * 80)
        upload_merged_data()
        print(f"Upload merged dataframe file to Google Drive - Done - Runtime: {int(time.time() - start)}s")

    print("#" * 80)
    print("Data collection pipeline completed successfully!")
    end_main = time.time()
    print(f"Runtime: {int(end_main - start_main)}s")
    print("#" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data collection pipeline")
    parser.add_argument("--no-upload", action="store_true", help="Skip Google Drive upload")
    args = parser.parse_args()
    
    main(upload_google_drive=not args.no_upload)

