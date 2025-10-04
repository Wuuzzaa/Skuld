import pandas as pd
import yfinance as yf
import time
import sys
import os
from datetime import datetime

# Import config and helpers for backward compatibility
from config import PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER, TABLE_STOCK_PRICE
from config_utils import get_filtered_symbols_with_logging
from src.database import insert_into_table, truncate_table


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


def fetch_current_prices(symbols, batch_size=50, delay=0.5):
    """
    Fetch current prices for a list of symbols using yfinance in batches.

    Returns a DataFrame with columns: symbol, live_stock_price, price_source, live_price_timestamp
    """
    symbols = list(dict.fromkeys([s for s in symbols if s]))  # unique, preserve order, filter falsy
    results = []

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        tickers = yf.Tickers(' '.join(batch))

        for symbol in batch:
            try:
                ticker = tickers.tickers.get(symbol)
                price = None
                source = 'unknown'

                if ticker is not None:
                    # Try fast_info first for a lightweight value
                    fast = getattr(ticker, 'fast_info', None)
                    if fast and isinstance(fast, dict) and fast.get('lastPrice'):
                        price = float(fast.get('lastPrice'))
                        source = 'fast_info.lastPrice'
                    else:
                        info = getattr(ticker, 'info', {}) or {}
                        # prefer regularMarketPrice / currentPrice
                        for k, src in (('regularMarketPrice', 'regularMarketPrice'), ('currentPrice', 'currentPrice')):
                            if k in info and info[k]:
                                try:
                                    price = float(info[k])
                                    source = src
                                    break
                                except Exception:
                                    continue

                timestamp = datetime.now()
                results.append({'symbol': symbol, 'live_stock_price': price, 'price_source': source, 'live_price_timestamp': timestamp})
            except Exception as e:
                results.append({'symbol': symbol, 'live_stock_price': None, 'price_source': f'error:{type(e).__name__}', 'live_price_timestamp': datetime.now()})

        # small delay between batches to avoid bursts
        if i + batch_size < len(symbols):
            time.sleep(delay)
    
    df = pd.DataFrame(results)

    # --- Database Persistence ---
    truncate_table(TABLE_STOCK_PRICE)
    insert_into_table(
        table_name=TABLE_STOCK_PRICE,
        dataframe=df,
        if_exists="append"
    )
    return df


def ticker_to_symbol(ticker):
    """Convert a ticker string like 'NASDAQ:AAPL' to 'AAPL'."""
    if ':' in ticker:
        return ticker.split(':', 1)[1]
    return ticker

def fetch_current_prices3():
    """
    Fetch current prices for a list of symbols using yfinance in batches.

    Returns a DataFrame with columns: symbol, live_stock_price, price_source, live_price_timestamp
    """
    results = []

    yahoo_query = YahooQueryScraper.instance()
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
    truncate_table(TABLE_STOCK_PRICE)
    insert_into_table(
        table_name=TABLE_STOCK_PRICE,
        dataframe=df,
        if_exists="append"
    )
    return df

def merge_prices_to_dataframe(df, symbol_col='symbol', how='left', batch_size=50, delay=0.5):
    """
    Fetch current prices for symbols that appear in `df` and return df merged with price columns.

    The function does not modify the original df (returns a new DataFrame).
    """
    if symbol_col not in df.columns:
        raise ValueError(f"symbol_col '{symbol_col}' not found in dataframe")

    symbols = df[symbol_col].dropna().astype(str).unique().tolist()
    prices_df = fetch_current_prices(symbols, batch_size=batch_size, delay=delay)

    merged = df.merge(prices_df, left_on=symbol_col, right_on='symbol', how=how)

    # drop the redundant 'symbol' column from the right side if present
    if 'symbol_y' in merged.columns and 'symbol_x' in merged.columns:
        merged = merged.rename(columns={'symbol_x': symbol_col}).drop(columns=['symbol_y'])

    return merged


if __name__ == '__main__':
    # quick local test when run as a script
    sample_symbols = ['AAPL', 'MSFT', 'GOOG']
    print('Fetching current prices for sample symbols...')
    df = fetch_current_prices(sample_symbols)
    print(df.to_string(index=False))


def get_live_stock_prices():
    """Backward-compatible wrapper used by older pipeline code.

    Fetches current prices for the configured symbol list and writes them to
    `PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER` so existing merge steps keep working.
    """
    try:
        symbols, _ = get_filtered_symbols_with_logging("Live Stock Prices")
    except Exception:
        # Fallback: no symbol list available
        symbols = []

    if not symbols:
        print("No symbols found to fetch live prices for.")
        return False

    df_prices = fetch_current_prices(symbols)
    try:
        df_prices.to_feather(PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER)
        print(f"Saved live prices to: {PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER}")
        return True if not df_prices.empty else False
    except Exception as e:
        print(f"Could not save live prices to feather: {e}")
        return False
