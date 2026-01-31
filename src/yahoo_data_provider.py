import logging
import time
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from yahooquery import Ticker


# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import (
    TABLE_FUNDAMENTAL_DATA_YAHOO,
    TABLE_EARNING_DATES,
    TABLE_STOCK_PRICE,
    TABLE_DIVIDENDS,
    YAHOO_HISTORY_PERIOD,
    YAHOO_HISTORY_INTERVAL
)
from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper
from config_utils import get_filtered_symbols_with_logging

logger = logging.getLogger(__name__)


def generate_fundamental_data():

    """
    Main function to generate fundamental data - called from main.py
    Uses ALL available yahooquery endpoints to get COMPLETE fundamentals (200+ columns)
    
    Args:
        enable_diagnostics (bool): If True, enables detailed column analysis logging
                                 If False, runs normal processing without diagnostic output
    """

    print("Processing fundamentals: collecting ALL available metrics from multiple endpoints...")
    
    symbols = get_filtered_symbols_with_logging("Yahoo Fundamentals")

    # Method 1: Get ALL financial data using all_financial_data (200+ columns)
    print("Fetching comprehensive financial data using all_financial_data()...")
    yahoo_query = YahooQueryScraper.instance()
    df_all_financial = yahoo_query.get_all_financial_data()
    
    if df_all_financial is not None and not df_all_financial.empty:

        # Get latest data per symbol
        if 'asOfDate' in df_all_financial.columns:
            df_all_financial['asOfDate'] = pd.to_datetime(df_all_financial['asOfDate'])
            idx = df_all_financial.groupby('symbol')['asOfDate'].idxmax()
            df_financial_latest = df_all_financial.loc[idx].reset_index(drop=True)
        else:
            df_financial_latest = df_all_financial.groupby('symbol').last().reset_index()
        
        print(f"[OK] Collected {df_financial_latest.shape[1]} columns from all_financial_data")
    else:
        # Fallback: create empty dataframe with symbol column
        df_financial_latest = pd.DataFrame({'symbol': symbols})
        print("[WARN] all_financial_data returned empty - using fallback")
    
    # Method 2: Add additional data from specific endpoints for completeness
    all_fundamental_data = []
    
    yahoo_query = YahooQueryScraper.instance()
    data = yahoo_query.get_modules()

    for symbol, symbol_data in data.items():
        try:
            # Start with financial data if available
            if symbol in df_financial_latest['symbol'].values:
                symbol_dict = df_financial_latest[df_financial_latest['symbol'] == symbol].iloc[0].to_dict()
            else:
                symbol_dict = {'symbol': symbol}
            
            # Add KEY_STATS data
            try:
                key_stats = symbol_data.get('defaultKeyStatistics')

                # Add all key_stats with prefix to avoid conflicts
                for key, value in key_stats.items():
                    symbol_dict[f'KeyStats_{key}'] = value
                
                # Calculate Forward EPS Growth using earnings_trend
                try:
                    earnings_trend = symbol_data.get('earningsTrend')
                    if 'trend' in earnings_trend:
                        trend = earnings_trend['trend']
                        next_year = next((x for x in trend if x['period'] == '+1y'), None)
                        if next_year and 'earningsEstimate' in next_year:
                            eps_next_year = next_year['earningsEstimate'].get('avg')
                            trailing_eps = key_stats.get('trailingEps')
                            
                            if trailing_eps and eps_next_year and trailing_eps > 0:
                                symbol_dict['Forward_EPS_Growth_Percent'] = ((eps_next_year - trailing_eps) / trailing_eps) * 100
                except Exception:
                    pass
            except Exception:
                pass
            
            # Add SUMMARY_DETAIL data  
            try:
                summary_detail = symbol_data.get('summaryDetail')
                if isinstance(summary_detail, dict):
                    # Add all summary_detail with prefix to avoid conflicts
                    for key, value in summary_detail.items():
                        symbol_dict[f'Summary_{key}'] = value
            except Exception:
                pass
            
            # Add FINANCIAL_DATA 
            try:
                financial_data = symbol_data.get('financialData')
                if isinstance(financial_data, dict):
                    # Add all financial_data with prefix to avoid conflicts
                    for key, value in financial_data.items():
                        symbol_dict[f'FinData_{key}'] = value
            except Exception:
                pass

            # Add CALENDAR_EVENTS (Earnings dates, Dividend dates)
            try:
                calendar_events = symbol_data.get('calendarEvents')
                if isinstance(calendar_events, dict):
                    for key, value in calendar_events.items():
                        # value can be complex (like earnings dict), convert to str if needed or flatten
                        if isinstance(value, dict) and key == 'earnings':
                             # Extract earnings dates if simpler format needed, 
                             # but here we just dump it or specific fields
                             # For flat files/DB, flattening is better. 
                             # 'earningsDate': ['2025-07-30 10:00S']
                             if 'earningsDate' in value:
                                 symbol_dict['Calendar_EarningsDate'] = str(value['earningsDate'])
                        else:
                            symbol_dict[f'Calendar_{key}'] = value
            except Exception:
                pass
            
            all_fundamental_data.append(symbol_dict)
            
        except Exception as e:
            print(f"Error processing data for {symbol}: {e}")
            all_fundamental_data.append({'symbol': symbol})
    
    if all_fundamental_data is None or len(all_fundamental_data) == 0:
        print("No fundamental data collected")
        return
    
    # Create comprehensive DataFrame from all collected data
    df_all_fundamentals = pd.DataFrame(all_fundamental_data)

    # Apply fixes for known issues
    if 'KeyStats_lastSplitDate' in df_all_fundamentals.columns:
        df_all_fundamentals['KeyStats_lastSplitDate'] = df_all_fundamentals['KeyStats_lastSplitDate'].astype(str)
    df_all_fundamentals = df_all_fundamentals.replace(
        ['Infinity', '-Infinity', 'inf', '-inf', np.inf, -np.inf], 
        np.nan
    )
    object_columns = df_all_fundamentals.select_dtypes(include='object').columns
    for col in object_columns:
        try:
            df_all_fundamentals[col] = df_all_fundamentals[col].astype(str)
        except Exception:
            pass

    insert_into_table(
        table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
        dataframe=df_all_fundamentals,
        if_exists="append"
    )
    
    # Additionally populate the specific EarningDates table reusing the same cached data
    fetch_and_save_earning_dates(data)


def fetch_and_save_earning_dates(cached_data=None):
    """
    Extracts earning dates from YahooQuery modules and saves to TABLE_EARNING_DATES.
    Can accept cached_data to avoid re-fetching.
    """
    logger.info("Extracting Earning Dates...")
    
    if cached_data is None:
        yahoo_query = YahooQueryScraper.instance()
        cached_data = yahoo_query.get_modules()
        
    earnings_dates = {}

    for symbol, symbol_data in cached_data.items():
        calendar_data = symbol_data.get('calendarEvents')

        try:
            # calendarEvents -> earnings -> earningsDate -> list
            raw_date = calendar_data['earnings']['earningsDate'][0][:10]  # e.g. '2025-07-30'
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            earnings_dates[symbol] = formatted_date
        except (TypeError, IndexError, KeyError, ValueError):
            # Fallback or skip
            # earnings_dates[symbol] = "No date" # Optional: decide if we want rows for missing dates
            pass

    if not earnings_dates:
        logger.info("No earning dates found to save.")
        return

    # store dataframe
    df = pd.DataFrame(list(earnings_dates.items()), columns=['symbol', 'earnings_date'])
    
    # --- Database Persistence ---
    truncate_table(TABLE_EARNING_DATES)
    insert_into_table(
        table_name=TABLE_EARNING_DATES,
        dataframe=df,
        if_exists="append"
    )
    logger.info(f"Saved {len(df)} earning dates to {TABLE_EARNING_DATES}")

def get_last_price_date(symbol):
    """
    [TODO: DB DEVELOPER] Get the last available price DATE from the database for Delta-Load.
    
    INSTRUCTIONS FOR DB DEVELOPER:
    -----------------------------
    1. Implement a SQL query to check the 'StockPrice' table.
    2. Select the MAX(Date) for the given 'symbol'.
    3. Return that date as a python datetime object.
    4. If no data exists for the symbol, return None.
    
    Current implementation is a STUB returning None (Forces full history load).
    """
    return None

def get_last_dividend_date(symbol):
    """
    [TODO: DB DEVELOPER] Get the last available dividend DATE from the database.
    
    INSTRUCTIONS FOR DB DEVELOPER:
    -----------------------------
    1. Implement a SQL query to check the 'Dividends' table (or equivalent).
    2. Select the MAX(Date) for the given 'symbol'.
    3. Return that date as a python datetime object.
    4. If no data exists, return None.
    
    Current implementation is a STUB returning None (Forces full history load).
    """
    return None

def should_fetch_dividends(symbol):
    """
    [TODO: DB DEVELOPER] Logic to skip redundant dividend checks (Optimization).
    
    INSTRUCTIONS FOR DB DEVELOPER:
    -----------------------------
    1. Get the last dividend payment date for this symbol from the DB.
    2. If (Today - LastPaymentDate) < 60 days (approx. quarter buffer), return False.
       -> This prevents querying Yahoo API for stocks that just paid a dividend.
    3. Return True if the check is needed (date unknown or long ago).
    
    Current implementation returns True (Always check).
    """
    # Defaults to True (always check) until implemented
    return True

def fetch_historical_prices():
    """Fetch OHLCV data and save to DB."""
    context_name = "Yahoo Historical Prices"
    logger.info(f"Starting {context_name} collection...")
    
    symbols = get_filtered_symbols_with_logging(context_name)
    all_dfs = []
    
    for symbol in symbols:
        try:
            last_date = get_last_price_date(symbol)
            if last_date:
                start_date = last_date + timedelta(days=1)
                period = None
                logger.info(f"Fetching price delta for {symbol} from {start_date}")
            else:
                start_date = None
                period = YAHOO_HISTORY_PERIOD
            
            ticker = Ticker(symbol)
            # Use adj_ohlc=True if you want adjusted prices; usually explicit OHLC is preferred for DB
            if start_date:
                df = ticker.history(start=start_date, interval=YAHOO_HISTORY_INTERVAL)
            else:
                df = ticker.history(period=period, interval=YAHOO_HISTORY_INTERVAL)
            
            if isinstance(df, dict) or df.empty:
                continue
                
            df = df.reset_index()
            
            # Normalize Date
            if 'date' in df.columns:
                df.rename(columns={'date': 'Date'}, inplace=True)
            elif 'index' in df.columns:
                df.rename(columns={'index': 'Date'}, inplace=True)
                
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.tz_localize(None)

            # Columns needed for Prices: Open, High, Low, Close, Volume
            # Rename lower to Title
            rename_map = {'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'symbol': 'Symbol'}
            df.rename(columns=rename_map, inplace=True)
            
            # Keep only relevant columns
            cols = ['Symbol', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']
            # Ensure they exist
            final_cols = [c for c in cols if c in df.columns]
            
            all_dfs.append(df[final_cols])
            
        except Exception as e:
            logger.error(f"Error fetching prices for {symbol}: {e}", exc_info=True)
            continue
            
    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        
        # [TODO: DB DEVELOPER]
        # Implement logic to save 'final_df' to the 'StockPrice' table.
        # Ensure efficient bulk insertion and handling of duplicates if necessary.
        #
        # Example (commented out):
        # insert_into_table(
        #     table_name=TABLE_STOCK_PRICE,
        #     dataframe=final_df,
        #     if_exists="append"
        # )
        
        logger.info(f"[Mock] Processed {len(final_df)} price rows (DB save pending implementation)")
    else:
        logger.warning("No price data collected.")

def fetch_dividends():
    """Fetch Dividend data and save to DB."""
    context_name = "Yahoo Dividends"
    logger.info(f"Starting {context_name} collection...")
    
    symbols = get_filtered_symbols_with_logging(context_name)
    all_dfs = []
    
    for symbol in symbols:
        if not should_fetch_dividends(symbol):
            continue
            
        try:
            # For dividends, yahooquery history often includes them, 
            # OR we can use dividend_history() if available, but history() is robust.
            # We'll use history(period='max') or scoped to be safe, filtering for 'dividends' > 0
            
            last_date = get_last_dividend_date(symbol)
            if last_date:
                 start_date = last_date + timedelta(days=1)
                 period = None
            else:
                 start_date = None
                 period = YAHOO_HISTORY_PERIOD # Check full history if nothing in DB
            
            ticker = Ticker(symbol)
            if start_date:
                df = ticker.history(start=start_date, interval='1d')
            else:
                df = ticker.history(period=period, interval='1d')
                
            if isinstance(df, dict) or df.empty:
                continue
            
            df = df.reset_index()
            
            # Normalize Date
            if 'date' in df.columns:
                df.rename(columns={'date': 'Date'}, inplace=True)
            elif 'index' in df.columns:
                df.rename(columns={'index': 'Date'}, inplace=True)
            
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.tz_localize(None)

            # Check for dividends col
            if 'dividends' in df.columns:
                # Filter rows where dividends > 0
                div_df = df[df['dividends'] > 0].copy()
                
                if not div_df.empty:
                    # Rename
                    div_df.rename(columns={'dividends': 'Dividend', 'symbol': 'Symbol'}, inplace=True)
                    # Keep cols
                    cols = ['Symbol', 'Date', 'Dividend']
                    final_cols = [c for c in cols if c in div_df.columns]
                    all_dfs.append(div_df[final_cols])
            
        except Exception as e:
            logger.error(f"Error fetching dividends for {symbol}: {e}", exc_info=True)
            continue
            
    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        
        # [TODO: DB DEVELOPER]
        # Implement logic to save 'final_df' to the 'Dividends' table.
        # 
        # Example (commented out):
        # insert_into_table(
        #     table_name=TABLE_DIVIDENDS,
        #     dataframe=final_df,
        #     if_exists="append"
        # )
        
        logger.info(f"[Mock] Processed {len(final_df)} dividend rows (DB save pending implementation)")
    else:
        logger.info("No new dividends found.")

if __name__ == "__main__":

    # Setup basic logging for standalone run
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    start = time.time()
    
    # Run Historical Data Fetch
    # fetch_historical_prices()
    # fetch_dividends()
    
    # internal testing of fundamental data (includes earning dates and dividend calendars)
    # generate_fundamental_data()
    
    end = time.time()
    duration = end - start

    logger.info(f"Runtime: {duration:.4f} seconds")
