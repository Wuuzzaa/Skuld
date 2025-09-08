import sys
import os

from src.database import insert_into_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yahooquery import Ticker
from datetime import datetime
from config import *
from config_utils import get_filtered_symbols_with_logging
import pandas as pd


def scrape_earning_dates():
    symbols = get_filtered_symbols_with_logging("Yahoo Earning Dates")

    tickers = Ticker(symbols, asynchronous=True)
    earnings_dates = {}

    for symbol, data in tickers.calendar_events.items():
        try:
            raw_date = data['earnings']['earningsDate'][0][:10]  # e.g. '2025-07-30'
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            earnings_dates[symbol] = formatted_date
        except (TypeError, IndexError) as e:
            earnings_dates[symbol] = "No date or no stock"

    # store dataframe
    df = pd.DataFrame(list(earnings_dates.items()), columns=['symbol', 'earnings_date'])
    df.to_feather(PATH_DATAFRAME_EARNING_DATES_FEATHER)
    # --- Database Persistence ---
    insert_into_table(
        table_name=TABLE_EARNING_DATES,
        dataframe=df,
        if_exists="replace"
    )

if __name__ == '__main__':
    import time

    start = time.time()
    scrape_earning_dates()
    end = time.time()

    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")

    # Runtime: 8.5962 seconds Async
    # Runtime: 61.5521
