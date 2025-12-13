import pandas as pd
import requests
import os
from yahooquery import Ticker
from datetime import datetime, timedelta
import time

# Define paths
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
RSL_DATA_FILE = os.path.join(DATA_DIR, 'rsl_strategy_data.feather')

import io

def get_sp500_symbols():
    """
    Fetches the current list of S&P 500 symbols from Wikipedia.
    """
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tables = pd.read_html(io.StringIO(response.text))
        df = tables[0]
        # Replace dots with dashes for Yahoo Finance (e.g. BRK.B -> BRK-B)
        symbols = df['Symbol'].apply(lambda x: x.replace('.', '-')).tolist()
        return symbols
    except Exception as e:
        print(f"Error fetching S&P 500 symbols: {e}")
        return []

def calculate_rsl_strategy(force_update=False):
    """
    Calculates the RSL strategy ranking.
    Returns a DataFrame with columns: symbol, close, SMA_26, RSL, Rank, date.
    """
    # Check if we have recent data
    if not force_update and os.path.exists(RSL_DATA_FILE):
        try:
            file_time = datetime.fromtimestamp(os.path.getmtime(RSL_DATA_FILE))
            # If data is less than 24 hours old, use it
            if datetime.now() - file_time < timedelta(hours=24):
                print("Loading RSL data from cache...")
                return pd.read_feather(RSL_DATA_FILE)
        except Exception as e:
            print(f"Error reading cache: {e}")

    print("Recalculating RSL strategy data...")
    symbols = get_sp500_symbols()
    if not symbols:
        print("No symbols found.")
        return pd.DataFrame()
    
    # Fetch data
    # We need 26 weeks of data for SMA. Fetching 1 year (52 weeks) is safe.
    # Interval: 1wk (weekly)
    
    # Batching symbols to avoid potential timeouts or large payloads
    batch_size = 500 
    all_results = []
    
    # Split symbols into batches
    symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    
    for batch in symbol_batches:
        try:
            tickers = Ticker(batch, asynchronous=True)
            # Fetch history
            df_hist = tickers.history(period='1y', interval='1wk')
            
            if df_hist.empty:
                continue
                
            if isinstance(df_hist.index, pd.MultiIndex):
                df_hist = df_hist.reset_index()
            
            # Ensure date is datetime and UTC
            if 'date' in df_hist.columns:
                df_hist['date'] = pd.to_datetime(df_hist['date'], utc=True)

            # Ensure we have 'symbol' column
            if 'symbol' not in df_hist.columns:
                # If only one symbol, it might not have symbol column if not reset properly or different structure
                # But with list of symbols, it should have it.
                # If index was symbol, date, reset_index should have created 'symbol'.
                pass

            # Group by symbol and calculate
            for symbol, group in df_hist.groupby('symbol'):
                # Need at least 26 data points
                if len(group) < 26:
                    continue
                
                group = group.sort_values('date')
                
                # Calculate SMA 26 on 'close'
                # Note: Yahoo Finance 'close' is adjusted for splits but not dividends usually? 
                # 'adjclose' is adjusted for both. 
                # Transcript says "Schlusskurs". Usually RSL uses Close. 
                # However, for long term comparison, Adj Close is safer. 
                # But let's stick to 'close' as it's standard for this strategy often.
                # Actually, if we use 'close', we might have issues with splits if they happened recently?
                # Yahoo 'close' is usually split-adjusted in history() call? 
                # Let's use 'adjclose' if available, else 'close'.
                
                price_col = 'adjclose' if 'adjclose' in group.columns else 'close'
                
                group['SMA_26'] = group[price_col].rolling(window=26).mean()
                
                # Get latest valid data point
                latest = group.iloc[-1]
                
                # If latest SMA is NaN (shouldn't be if len >= 26), skip
                if pd.isna(latest['SMA_26']):
                    continue
                    
                rsl = latest[price_col] / latest['SMA_26']
                
                all_results.append({
                    'symbol': symbol,
                    'close': latest[price_col],
                    'SMA_26': latest['SMA_26'],
                    'RSL': rsl,
                    'date': latest['date']
                })
                
        except Exception as e:
            print(f"Error processing batch: {e}")
            
    df_results = pd.DataFrame(all_results)
    
    if not df_results.empty:
        # Rank by RSL descending
        df_results = df_results.sort_values('RSL', ascending=False).reset_index(drop=True)
        df_results['Rank'] = df_results.index + 1
        
        # Save to feather
        try:
            df_results.to_feather(RSL_DATA_FILE)
            print(f"Saved RSL data to {RSL_DATA_FILE}")
        except Exception as e:
            print(f"Error saving RSL data: {e}")
            
    return df_results

if __name__ == "__main__":
    # Test run
    df = calculate_rsl_strategy(force_update=True)
    print(df.head())
