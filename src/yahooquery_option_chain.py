import time
import sys
import os
import pandas as pd

from config import TABLE_OPTION_DATA_YAHOO
from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def get_yahooquery_option_chain():
    yahoo_query = YahooQueryScraper.instance()
    df: pd.DataFrame = yahoo_query.get_option_chain()

    print(f"Total options collected: {len(df)}")

    # Process the combined data
    df = df.rename(columns={
        'symbol': 'symbol',
        'expiration': 'expiration_date',
        'optionType': 'option-type',
        'volume': 'option_volume',
        'openInterest': 'option_open_interest',
    })

    # --- Database Persistence ---
    truncate_table(TABLE_OPTION_DATA_YAHOO)
    insert_into_table(
        table_name=TABLE_OPTION_DATA_YAHOO,
        dataframe=df,
        if_exists="append"
    )

if __name__ == '__main__':
    start = time.time()
    get_yahooquery_option_chain()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")