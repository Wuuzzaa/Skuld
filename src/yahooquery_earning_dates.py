import sys
import os

from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yahooquery import Ticker
from datetime import datetime
from config import *
import pandas as pd

def scrape_earning_dates():
    earnings_dates = {}

    yahoo_query = YahooQueryScraper.instance()
    data = yahoo_query.get_modules()


    for symbol, symbol_data in data.items():
        calendar_data = symbol_data.get('calendarEvents')

        try:
            raw_date = calendar_data['earnings']['earningsDate'][0][:10]  # e.g. '2025-07-30'
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            earnings_dates[symbol] = formatted_date
        except (TypeError, IndexError) as e:
            earnings_dates[symbol] = "No date or no stock"

    # store dataframe
    df = pd.DataFrame(list(earnings_dates.items()), columns=['symbol', 'earnings_date'])
    # --- Database Persistence ---
    truncate_table(TABLE_EARNING_DATES)
    insert_into_table(
        table_name=TABLE_EARNING_DATES,
        dataframe=df,
        if_exists="append"
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
