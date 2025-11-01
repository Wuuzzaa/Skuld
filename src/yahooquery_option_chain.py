import pandas as pd
import time
import sys
import os

from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from yahooquery import Ticker

def get_yahooquery_option_chain():
    yahoo_query = YahooQueryScraper.instance()
    df = yahoo_query.get_option_chain()

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

def get_live_stock_prices(symbols):
    """Get live stock prices for unique symbols only"""
    unique_symbols = list(set(symbols))
    prices = {}
    
    for symbol in unique_symbols:
        try:
            # Use yfinance to get current price
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            if not hist.empty:
                prices[symbol] = hist['Close'].iloc[-1]
            else:
                prices[symbol] = None
        except Exception as e:
            print(f"Error getting price for {symbol}: {e}")
            prices[symbol] = None
    
    return prices


if __name__ == '__main__':
    start = time.time()
    get_yahooquery_option_chain()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")