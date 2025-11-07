import argparse
import time
import logging
from src.data_collector import run_data_collection_pipeline
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
    logger.info(f"Config: upload_df_google_drive: {upload_google_drive}\n")

    run_data_collection_pipeline()
    
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

