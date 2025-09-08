import pandas as pd
import time
import sys
import os

from src.database import insert_into_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import get_filtered_symbols_with_logging
from yahooquery import Ticker


def get_yahooquery_option_chain():
    # Test mode logic and logging centrally from config
    symbols = get_filtered_symbols_with_logging("Yahoo Option Chain")

    all_option_data = []
    successful_symbols = []
    failed_symbols = []

    for symbol in symbols:
        try:
            print(f"Fetching option chain for {symbol}...")
            ticker = Ticker(symbol)
            df = ticker.option_chain
            
            if df is not None and not df.empty:
                # symbol expiration_date and option-type from index to column
                df = df.reset_index()
                all_option_data.append(df)
                successful_symbols.append(symbol)
                print(f"SUCCESS {symbol}: {len(df)} options found")
            else:
                print(f"WARNING {symbol}: No option data available")
                failed_symbols.append(symbol)
                
        except Exception as e:
            print(f"ERROR {symbol}: Error fetching options - {str(e)}")
            failed_symbols.append(symbol)
        
        # Small delay to avoid rate limiting
        time.sleep(0.1)

    if not all_option_data:
        print("WARNING: No option data found for any symbols")
        return
    
    # Combine all data
    df = pd.concat(all_option_data, ignore_index=True)
    
    print(f"\n=== SUMMARY ===")
    print(f"Successfully processed: {len(successful_symbols)} symbols")
    print(f"Failed: {len(failed_symbols)} symbols")
    if failed_symbols:
        print(f"Failed symbols: {failed_symbols}")
    print(f"Total options collected: {len(df)}")

    # Process the combined data
    df = df.rename(columns={
        'symbol': 'symbol',
        'expiration': 'expiration_date',
        'optionType': 'option-type',
        'volume': 'option_volume',
        'openInterest': 'option_open_interest',
    })

    df.to_feather(PATH_DATAFRAME_YAHOOQUERY_OPTION_CHAIN_FEATHER)
    print(f"SUCCESS: Yahoo option chain data saved to: {PATH_DATAFRAME_YAHOOQUERY_OPTION_CHAIN_FEATHER}")

    # --- Database Persistence ---
    insert_into_table(
        table_name=TABLE_OPTION_DATA_YAHOO,
        dataframe=df,
        if_exists="replace"
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
