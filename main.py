import argparse
from src.database import run_migrations, select_into_dataframe, truncate_table
from src.feature_engineering import feature_construction
from src.optiondata_feathers_to_df_merge import combine_feather_files
from src.tradingview_optionchain_scrapper import scrape_option_data
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.merge_feather_dataframes_data import merge_data_dataframes
from src.util import create_all_project_folders, get_option_expiry_dates, clean_temporary_files, clean_all_data_files
from src.yahooquery_earning_dates import scrape_earning_dates
from src.yahooquery_option_chain import get_yahooquery_option_chain
from src.yahooquery_financials import generate_fundamental_data
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *
from src.google_drive_upload import upload_merged_data
from src.dividend_radar import process_dividend_data
from config_utils import get_filtered_symbols_and_dates_with_logging
import pandas as pd


def main(upload_df_google_drive=True):
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
    
    print(f"upload_df_google_drive: {upload_df_google_drive}\n")
    print("#" * 80)

    # CLEAN temporary files from previous runs
    # Use clean_all_data_files() for complete cleanup, clean_temporary_files() for normal cleanup
    clean_temporary_files()  # Change to clean_all_data_files() if you want complete cleanup

    create_all_project_folders()

    print("#"*80)
    print("Get Yahoo Finance data")
    print("#" * 80)
    scrape_yahoo_finance_analyst_price_targets()
    print("Get Yahoo Finance data - Done")

    print("#" * 80)
    print("Get option data")
    print("#" * 80)

    # NEW: Centralized config-driven data collection
    # Get expiry dates as strings in YYYY-MM-DD format for filtering
    from config_utils import generate_expiry_dates_from_rules
    expiry_date_strings = generate_expiry_dates_from_rules()
    symbols_to_use, filtered_expiry_dates = get_filtered_symbols_and_dates_with_logging(
        expiry_date_strings, "Option Data Collection"
    )
    
    # Convert filtered dates back to integers for scraping functions
    expiry_dates_int = [int(date_str.replace("-", "")) for date_str in filtered_expiry_dates]

    print(f"Collecting data for {len(symbols_to_use)} symbols and {len(expiry_dates_int)} expiry dates")
    truncate_table(TABLE_OPTION_DATA_TRADINGVIEW)
    for expiration_date in expiry_dates_int:
        for symbol in symbols_to_use:
            scrape_option_data(
                symbol=symbol,
                expiration_date=expiration_date,
                exchange=SYMBOLS_EXCHANGE[symbol],
                folderpath=PATH_OPTION_DATA_TRADINGVIEW
            )

    print("Get option data - Done")

    print("#" * 80)
    print("Combine option data JSON to feather")
    print("#" * 80)
    combine_feather_files(folder_path=PATH_OPTION_DATA_TRADINGVIEW, data_feather_path=PATH_DATAFRAME_OPTION_DATA_FEATHER)
    print("Combine option data JSON to feather - Done")

    print("#" * 80)
    print("Get price and technical indicators")
    print("#" * 80)
    scrape_and_save_price_and_technical_indicators()
    print("Get price and technical indicators - Done")

    print("#" * 80)
    print("Dividend Radar")
    print("#" * 80)
    process_dividend_data(path_outputfile=PATH_DIVIDEND_RADAR)
    # Debug: Check if Classification exists in dividend data
    df_div = pd.read_feather(PATH_DIVIDEND_RADAR)
    print("Dividend Radar columns:", df_div.columns.tolist())
    print("Has Classification?", 'Classification' in df_div.columns)
    if 'Classification' in df_div.columns:
        print("Classification values:", df_div['Classification'].value_counts())
    print("Dividend Radar - Done")

    print("#" * 80)
    print("Earning Dates")
    print("#" * 80)
    scrape_earning_dates()
    print("Earning Dates - Done")

    print("#" * 80)
    print("Yahoo Query Option Chain")
    print("#" * 80)
    get_yahooquery_option_chain()
    print("Yahoo Query Option Chain - Done")

    print("#" * 80)
    print("Yahoo Query Fundamentals")
    print("#" * 80)
    generate_fundamental_data()
    print("Yahoo Query Fundamentals - Done")


    print("#" * 80)
    print("Merge all feather dataframe files (with live prices)")
    print("#" * 80)
    merge_data_dataframes()
    # Debug: Check merged data
    df_merged = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    print("Final columns:", df_merged.columns.tolist())
    print("Has Classification?", 'Classification' in df_merged.columns)
    print("Merge all feather dataframe files - Done")

    print("#" * 80)
    print("Feature engineering")
    print("#" * 80)
    feature_construction()
    print("Feature engineering - Done")

    if upload_df_google_drive:
        print("#" * 80)
        print("Upload file to Google Drive")
        print("#" * 80)
        upload_merged_data()
        print("Upload file to Google Drive - Done")

    print("#" * 80)
    print("Data collection pipeline completed successfully!")
    print("#" * 80)

    # Beispiel
    df = select_into_dataframe("SELECT * FROM OptionDataMerged")
    print(f"Total rows in OptionDataMerged: {len(df)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data collection pipeline")
    parser.add_argument("--no-upload", action="store_true", help="Skip Google Drive upload")
    args = parser.parse_args()
    
    main(upload_df_google_drive=not args.no_upload)
