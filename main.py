import argparse
import time
import logging
from src.logger_config import setup_logging
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

# enable logging
setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info("Start SKULD")


def main(upload_google_drive=True):
    start_main = time.time()
    run_migrations()
    logger.info("#" * 80)
    logger.info(f"Starting Data Collection Pipeline")

    logger.info(f"Symbol selection mode: {SYMBOL_SELECTION['mode']}")

    # Show configuration summary
    enabled_rules = [rule for rule in OPTIONS_COLLECTION_RULES if rule.get("enabled", False)]
    logger.info(f"[INFO] Enabled collection rules: {len(enabled_rules)}")
    for rule in enabled_rules:
        logger.info(f"  - {rule['name']}: {rule['days_range']} days, {rule['frequency']}")

    if SYMBOL_SELECTION.get("use_max_limit", False) and "max_symbols" in SYMBOL_SELECTION:
        logger.info(f"[INFO] Symbol limit: {SYMBOL_SELECTION['max_symbols']}")

    logger.info(f"upload_df_google_drive: {upload_google_drive}\n")
    logger.info("#" * 80)

    # CLEAN temporary files from previous runs
    # Use clean_all_data_files() for complete cleanup, clean_temporary_files() for normal cleanup
    clean_temporary_files()  # Change to clean_all_data_files() if you want complete cleanup

    create_all_project_folders()

    logger.info("#"*80)
    logger.info("Get Yahoo Finance data - Analyst Price Targets")
    start = time.time()
    logger.info("#" * 80)
    scrape_yahoo_finance_analyst_price_targets3()
    logger.info(f"Get Yahoo Finance data - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Get option data")
    logger.info("#" * 80)

    # NEW: Centralized config-driven data collection
    # Get expiry dates as strings in YYYY-MM-DD format for filtering
    expiry_date_strings = generate_expiry_dates_from_rules()
    symbols_to_use, filtered_expiry_dates = get_filtered_symbols_and_dates_with_logging(
        expiry_date_strings, "Option Data Collection"
    )

    # Convert filtered dates back to integers for scraping functions
    # expiry_dates_int = [int(date_str.replace("-", "")) for date_str in filtered_expiry_dates]

    # logger.info(f"Collecting data from Trading View for {len(symbols_to_use)} symbols and {len(expiry_dates_int)} expiry dates")
    logger.info(f"Collecting data from Trading View for {len(symbols_to_use)} symbols and all expiration dates")

    start = time.time()
    scrape_option_data_trading_view(symbols_to_use)

    logger.info(f"Get option data from Trading View - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Get price and technical indicators")
    start = time.time()
    logger.info("#" * 80)
    scrape_and_save_price_and_technical_indicators()
    logger.info(f"Get price and technical indicators - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Dividend Radar")
    start = time.time()
    logger.info("#" * 80)
    process_dividend_data(path_outputfile=PATH_DIVIDEND_RADAR)
    # Debug: Check if Classification exists in dividend data
    df_div = pd.read_feather(PATH_DIVIDEND_RADAR)
    logger.info("Dividend Radar columns:", df_div.columns.tolist())
    logger.info("Has Classification?", 'Classification' in df_div.columns)
    if 'Classification' in df_div.columns:
        logger.info("Classification values:", df_div['Classification'].value_counts())
    logger.info(f"Dividend Radar - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Earning Dates")
    start = time.time()
    logger.info("#" * 80)
    scrape_earning_dates2()
    logger.info(f"Earning Dates - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Yahoo Query Option Chain")
    start = time.time()
    logger.info("#" * 80)
    get_yahooquery_option_chain2()
    logger.info(f"Yahoo Query Option Chain - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Yahoo Query Fundamentals")
    start = time.time()
    logger.info("#" * 80)
    generate_fundamental_data2()
    logger.info(f"Yahoo Query Fundamentals - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Merge all feather dataframe files (with live prices)")
    start = time.time()
    logger.info("#" * 80)
    merge_data_dataframes()
    # Debug: Check merged data
    df_merged = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    logger.info("Final columns:", len(df_merged.columns.tolist()))
    logger.info("Has Classification?", 'Classification' in df_merged.columns)
    logger.info(f"Merge all feather dataframe files - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Feature engineering")
    start = time.time()
    logger.info("#" * 80)
    feature_construction()
    logger.info(f"Feature engineering - Done - Runtime: {int(time.time() - start)}s")

    if upload_google_drive:
        logger.info("#" * 80)
        logger.info("Upload database to Google Drive")
        start = time.time()
        logger.info("#" * 80)
        upload_database()
        logger.info(f"Upload database to Google Drive - Done - Runtime: {int(time.time() - start)}s")
        
        logger.info("#" * 80)
        logger.info("Upload merged dataframe file to Google Drive")
        start = time.time()
        logger.info("#" * 80)
        upload_merged_data()
        logger.info(f"Upload merged dataframe file to Google Drive - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Data collection pipeline completed successfully!")
    end_main = time.time()
    logger.info(f"Runtime: {int(end_main - start_main)}s")
    logger.info("#" * 80)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data collection pipeline")
    parser.add_argument("--no-upload", action="store_true", help="Skip Google Drive upload")
    args = parser.parse_args()
    
    main(upload_google_drive=not args.no_upload)

