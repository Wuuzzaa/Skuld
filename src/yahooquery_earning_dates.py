import sys
import os
import pandas as pd
from config import TABLE_EARNING_DATES
from src.database import get_postgres_engine, insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def scrape_earning_dates(symbols):
    earnings_dates = {}
    yahoo_query = YahooQueryScraper.instance(symbols)
    data = yahoo_query.get_modules(modules='calendarEvents')

    for symbol, symbol_data in data.items():
        calendar_data = symbol_data.get('calendarEvents')

        try:
            raw_date = calendar_data['earnings']['earningsDate'][0][:10]  # e.g. '2025-07-30'
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            earnings_dates[symbol] = formatted_date
        except (TypeError, IndexError) as e:
            earnings_dates[symbol] = None

    # store dataframe
    df = pd.DataFrame(list(earnings_dates.items()), columns=['symbol', 'earnings_date'])
    if len(df) == 0:
        raise Exception("No Data fetching earnings dates from Yahoo API")
    # --- Database Persistence ---
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_EARNING_DATES)
        insert_into_table(
            connection,
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