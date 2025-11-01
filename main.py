import argparse
import time
import logging
from src.live_stock_price_collector import fetch_current_prices
from src.logger_config import setup_logging
from src.database import run_migrations
from src.tradingview_optionchain_scrapper import scrape_option_data_trading_view
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.yahooquery_earning_dates import scrape_earning_dates
from src.yahooquery_option_chain import get_yahooquery_option_chain
from src.yahooquery_financials import generate_fundamental_data
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *
from src.google_drive_upload import upload_database
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

    logger.info("#"*80)
    logger.info("Get Yahoo Finance data - Analyst Price Targets")
    start = time.time()
    logger.info("#" * 80)
    scrape_yahoo_finance_analyst_price_targets()
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
    process_dividend_data()
    logger.info(f"Dividend Radar - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Earning Dates")
    start = time.time()
    logger.info("#" * 80)
    scrape_earning_dates()
    logger.info(f"Earning Dates - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Yahoo Query Option Chain")
    start = time.time()
    logger.info("#" * 80)
    get_yahooquery_option_chain()
    logger.info(f"Yahoo Query Option Chain - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Yahoo Query Fundamentals")
    start = time.time()
    logger.info("#" * 80)
    generate_fundamental_data()
    logger.info(f"Yahoo Query Fundamentals - Done - Runtime: {int(time.time() - start)}s")

    logger.info("#" * 80)
    logger.info("Fetch current stock prices")
    start = time.time()
    fetch_current_prices()
    logger.info(f"Fetch current stock prices - Done - Runtime: {int(time.time() - start)}s")

    if upload_google_drive:
        logger.info("#" * 80)
        logger.info("Upload database to Google Drive")
        start = time.time()
        logger.info("#" * 80)
        upload_database()
        logger.info(f"Upload database to Google Drive - Done - Runtime: {int(time.time() - start)}s")
        
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

