import pandas as pd
import sys
import os
from datetime import datetime
from config import TABLE_STOCK_PRICE
from src.database import get_postgres_engine, insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""
Simplified live price helper

This module provides two small helpers:
- fetch_current_prices(symbols): returns a DataFrame with current prices for the given symbols
- merge_prices_to_dataframe(df, symbol_col='symbol'): fetches prices for symbols present in `df` and returns df merged with live prices

No caching, no history requests — only immediate price lookups and a timestamp.
"""


def ticker_to_symbol(ticker):
    """Convert a ticker string like 'NASDAQ:AAPL' to 'AAPL'."""
    if ':' in ticker:
        return ticker.split(':', 1)[1]
    return ticker

def fetch_current_prices(symbols):
    """
    Fetch current prices for a list of symbols using yfinance in batches.

    Returns a DataFrame with columns: symbol, live_stock_price, price_source, live_price_timestamp
    """
    results = []

    yahoo_query = YahooQueryScraper.instance(symbols)
    data = yahoo_query.get_modules()


    for symbol, symbol_data in data.items():
        #https://yahooquery.dpguthrie.com/guide/ticker/modules/#price
        price_data = symbol_data.get('price')
        try:
            results.append({'symbol': symbol, 'live_stock_price': price_data['regularMarketPrice'], 'price_source': price_data['regularMarketSource'], 'live_price_timestamp': price_data['regularMarketTime']})
        except Exception as e:
                results.append({'symbol': symbol, 'live_stock_price': None, 'price_source': f'error:{type(e).__name__}', 'live_price_timestamp': datetime.now()})
    
    df = pd.DataFrame(results)

    # --- Database Persistence ---
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_PRICE)
        insert_into_table(
            connection,
            table_name=TABLE_STOCK_PRICE,
            dataframe=df,
            if_exists="append"
        )
    return df

if __name__ == '__main__':
    # quick local test when run as a script
    sample_symbols = ['AAPL', 'MSFT', 'GOOG']
    print('Fetching current prices for sample symbols...')
    df = fetch_current_prices(sample_symbols)
    print(df.to_string(index=False))

