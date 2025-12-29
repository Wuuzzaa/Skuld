import logging
import time
import sys
import os
import pandas as pd

from config import TABLE_OPTION_DATA_YAHOO
from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_yahooquery_option_chain():
    yahoo_query = YahooQueryScraper.instance()
    # --- Database Persistence ---
    truncate_table(TABLE_OPTION_DATA_YAHOO)

    total_options = 0
    generator = yahoo_query.get_option_chain()

    for df in generator:
        if df is None or df.empty:
            continue

        start_count = len(df)
        total_options += start_count

        # Process the batch data
        df = df.rename(columns={
            'symbol': 'symbol',
            'expiration': 'expiration_date',
            'optionType': 'option-type',
            'volume': 'option_volume',
            'openInterest': 'option_open_interest',
        })

        insert_into_table(
            table_name=TABLE_OPTION_DATA_YAHOO,
            dataframe=df,
            if_exists="append"
        )
    
    logger.info(f"Total options collected and saved: {total_options}")

if __name__ == '__main__':
    start = time.time()
    get_yahooquery_option_chain()
    end = time.time()
    duration = end - start

    logger.info(f"\nRuntime: {duration:.4f} seconds")