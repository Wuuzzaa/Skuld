import pandas as pd
import yfinance as yf
import time
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import validate_config, get_filtered_symbols_with_logging


def get_live_stock_prices():
    """
    Collect live stock prices for all symbols and save to feather file.
    This ensures each symbol is queried only once during data collection.
    """
    # Get symbols using centralized config logic
    symbols, active_mode = get_filtered_symbols_with_logging("Live Stock Prices")
    
    print(f"Collecting live stock prices for {len(symbols)} symbols...")
    
    stock_price_data = []
    successful_symbols = []
    failed_symbols = []
    
    # Batch processing for efficiency
    batch_size = 50  # Process in batches to avoid overwhelming yfinance
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    
    for batch_idx, i in enumerate(range(0, len(symbols), batch_size)):
        batch_symbols = symbols[i:i + batch_size]
        print(f"Processing batch {batch_idx + 1}/{total_batches}: {len(batch_symbols)} symbols")
        
        try:
            # Use yfinance to get batch data
            tickers = yf.Tickers(' '.join(batch_symbols))
            
            for symbol in batch_symbols:
                try:
                    ticker = tickers.tickers[symbol]
                    info = ticker.info
                    hist = ticker.history(period="1d", interval="1m")
                    
                    # Get current price from multiple sources for reliability
                    current_price = None
                    price_source = "unknown"
                    
                    # Try different price sources in order of preference
                    if not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
                        price_source = "1min_history"
                    elif 'currentPrice' in info and info['currentPrice']:
                        current_price = float(info['currentPrice'])
                        price_source = "current_price"
                    elif 'regularMarketPrice' in info and info['regularMarketPrice']:
                        current_price = float(info['regularMarketPrice'])
                        price_source = "regular_market"
                    elif 'previousClose' in info and info['previousClose']:
                        current_price = float(info['previousClose'])
                        price_source = "previous_close"
                    
                    if current_price and current_price > 0:
                        # Collect additional market data
                        stock_data = {
                            'symbol': symbol,
                            'live_stock_price': current_price,
                            'price_source': price_source,
                            'market_cap': info.get('marketCap', None),
                            'volume': info.get('volume', None),
                            'avg_volume': info.get('averageVolume', None),
                            'dividend_yield': info.get('dividendYield', None),
                            'trailing_pe': info.get('trailingPE', None),
                            'forward_pe': info.get('forwardPE', None),
                            'beta': info.get('beta', None),
                            '52_week_high': info.get('fiftyTwoWeekHigh', None),
                            '52_week_low': info.get('fiftyTwoWeekLow', None),
                            'live_price_timestamp': datetime.now(),
                            'market_state': info.get('marketState', 'unknown')
                        }
                        
                        stock_price_data.append(stock_data)
                        successful_symbols.append(symbol)
                        print(f"✅ {symbol}: ${current_price:.2f} ({price_source})")
                        
                    else:
                        failed_symbols.append(symbol)
                        print(f"❌ {symbol}: No valid price found")
                        
                except Exception as e:
                    failed_symbols.append(symbol)
                    print(f"❌ {symbol}: Error - {str(e)}")
                    continue
            
            # Small delay between batches to be respectful to the API
            if batch_idx < total_batches - 1:
                time.sleep(1)
                
        except Exception as e:
            print(f"❌ Batch {batch_idx + 1} failed: {str(e)}")
            failed_symbols.extend(batch_symbols)
            continue
    
    # Create DataFrame
    if stock_price_data:
        df_stock_prices = pd.DataFrame(stock_price_data)
        
        # Save to feather file
        print(f"\n💾 Saving live stock prices to: {PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER}")
        df_stock_prices.to_feather(PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER)
        
        # Print statistics
        success_rate = (len(successful_symbols) / len(symbols)) * 100
        print(f"\n📊 Live Stock Price Collection Statistics:")
        print(f"   Total symbols processed: {len(symbols)}")
        print(f"   Successful: {len(successful_symbols)} ({success_rate:.1f}%)")
        print(f"   Failed: {len(failed_symbols)} ({100-success_rate:.1f}%)")
        
        if failed_symbols:
            print(f"   Failed symbols: {', '.join(failed_symbols[:10])}{'...' if len(failed_symbols) > 10 else ''}")
        
        # Show sample data
        print(f"\n📋 Sample Data (first 3 rows):")
        print(df_stock_prices[['symbol', 'live_stock_price', 'price_source', 'market_cap', 'dividend_yield']].head(3).to_string())
        
        return True
    else:
        print("❌ No stock price data collected!")
        return False


def validate_live_stock_prices():
    """
    Validate the collected live stock price data.
    """
    try:
        df = pd.read_feather(PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER)
        
        print(f"\n🔍 Live Stock Price Data Validation:")
        print(f"   File: {PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER}")
        print(f"   Rows: {len(df):,}")
        print(f"   Columns: {len(df.columns)}")
        print(f"   Symbols: {df['symbol'].nunique()}")
        
        # Check for missing prices
        missing_prices = df['live_stock_price'].isna().sum()
        print(f"   Missing prices: {missing_prices}")
        
        # Price range validation
        if 'live_stock_price' in df.columns:
            price_stats = df['live_stock_price'].describe()
            print(f"   Price range: ${price_stats['min']:.2f} - ${price_stats['max']:.2f}")
            print(f"   Average price: ${price_stats['mean']:.2f}")
        
        # Check timestamp freshness
        if 'live_price_timestamp' in df.columns:
            latest_timestamp = pd.to_datetime(df['live_price_timestamp']).max()
            age_minutes = (datetime.now() - latest_timestamp).total_seconds() / 60
            print(f"   Data age: {age_minutes:.1f} minutes")
            
            if age_minutes > 60:
                print("   ⚠️  WARNING: Data is older than 1 hour")
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Live stock price file not found: {PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER}")
        return False
    except Exception as e:
        print(f"❌ Error validating live stock prices: {e}")
        return False


if __name__ == '__main__':
    """
    Run live stock price collection standalone for testing.
    """
    print("#" * 80)
    print("LIVE STOCK PRICE COLLECTION - STANDALONE TEST")
    print("#" * 80)
    
    start_time = time.time()
    
    success = get_live_stock_prices()
    
    if success:
        validate_live_stock_prices()
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\nRuntime: {duration:.2f} seconds")
    print("Done!")
