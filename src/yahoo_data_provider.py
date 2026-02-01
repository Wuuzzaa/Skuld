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
    Main function to generate fundamental data - called from main.py.
    Orchestrates the collection of Quantitative (Financials) and Qualitative (Profile) data.
    """
    logger.info("Processing fundamentals: collecting ALL available metrics...")
    
    # 1. Fetch Quantitative Data (Balance Sheet, Income Statement, etc.) - The "Financials"
    df_financials = _fetch_quantitative_data()
    
    # 2. Fetch Qualitative Data (Sector, Industry, Earnings Dates) - The "Modules"
    module_data = _fetch_qualitative_data()
    
    # 3. Merge & Flatten
    df_final = _merge_datasets(df_financials, module_data)
    
    if df_final is None or df_final.empty:
        logger.warning("No fundamental data generated.")
        return

    # 4. Save to DB
    logger.info(f"Saving {len(df_final)} rows with {df_final.shape[1]} columns to {TABLE_FUNDAMENTAL_DATA_YAHOO}...")
    try:
        # Pre-process numeric discrepancies
        if 'KeyStats_lastSplitDate' in df_final.columns:
            df_final['KeyStats_lastSplitDate'] = df_final['KeyStats_lastSplitDate'].astype(str)
            
        df_final = df_final.replace(
            ['Infinity', '-Infinity', 'inf', '-inf', np.inf, -np.inf], 
            np.nan
        )
        # Ensure objects are strings
        object_columns = df_final.select_dtypes(include='object').columns
        for col in object_columns:
            df_final[col] = df_final[col].astype(str)

        # -------------------------------------------------------------------------
        # [TODO: DB DEVELOPER] INSTRUCTIONS FOR 'FundamentalDataYahoo' TABLE
        # -------------------------------------------------------------------------
        # This DataFrame ('df_final') is a "Wide Table" containing 200+ columns
        # merging Financials (Balance Sheet, P&L) and Qualitative Data (Profile).
        #
        # STRATEGY:
        # 1. Primary Key: (Symbol, asOfDate) or just (Symbol) if preserving history is not needed.
        #    (Current logic gets the LATEST snapshot).
        # 2. Schema:
        #    - 'Symbol': VARCHAR(20) NOT NULL
        #    - 'Sector': VARCHAR(100)
        #    - 'Industry': VARCHAR(100)
        #    - 'Forward_EPS_Growth_Percent': FLOAT
        #    - 'asOfDate': DATE / DATETIME
        #    - ... plus ~200 dynamic columns from Yahoo (e.g., 'TotalAssets', 'EBITDA').
        #
        # RECOMMENDATION:
        # - Option A (Postgres): Use a JSONB column named 'raw_data' to store the 
        #   variable columns, keeping only key fields (Symbol, Sector) as explicit columns.
        # - Option B (Wide Table): Allow auto-creation of columns (current 'append' behavior).
        #   Ensure the DB user has permissions to ALTER TABLE/ADD COLUMN.
        # -------------------------------------------------------------------------

        insert_into_table(
            table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
            dataframe=df_final,
            if_exists="append"
        )
        
        # 5. Extract Earning Dates specifically (from the cached module data)
        # We reuse 'module_data' to avoid re-fetching
        _save_earning_dates(module_data)
        
    except Exception as e:
        logger.error(f"Error saving fundamental data: {e}", exc_info=True)


def _fetch_quantitative_data():
    """Fetches numeric financial data (Balance Sheet, Cash Flow, etc.) using all_financial_data endpoint."""
    logger.info("Step 1/3: Fetching comprehensive financial data (Quantitative)...")
    symbols = get_filtered_symbols_with_logging("Yahoo Fundamentals - Quantitative")
    
    yahoo_query = YahooQueryScraper.instance()
    df_all_financial = yahoo_query.get_all_financial_data()
    
    if df_all_financial is not None and not df_all_financial.empty:
        # Get latest snapshot per symbol
        if 'asOfDate' in df_all_financial.columns:
            df_all_financial['asOfDate'] = pd.to_datetime(df_all_financial['asOfDate'])
            idx = df_all_financial.groupby('symbol')['asOfDate'].idxmax()
            df_latest = df_all_financial.loc[idx].reset_index(drop=True)
        else:
            df_latest = df_all_financial.groupby('symbol').last().reset_index()
            
        logger.info(f"[OK] Collected {df_latest.shape[1]} financial indicators for {len(df_latest)} symbols")
        return df_latest
    else:
        logger.warning("[WARN] all_financial_data returned empty. Using symbol list default.")
        return pd.DataFrame({'symbol': symbols})

def _fetch_qualitative_data():
    """Fetches metadata modules (Profile, Key Stats, Calendar)."""
    logger.info("Step 2/3: Fetching metadata modules (Qualitative)...")
    yahoo_query = YahooQueryScraper.instance()
    return yahoo_query.get_modules()

def _merge_datasets(df_financials, module_data):
    """Enriches the financial dataframe with module metadata (Sector, etc)."""
    logger.info("Step 3/3: Merging datasets and flattening structure...")
    
    enriched_rows = []
    
    # Create a lookup dict for financial data rows
    financial_lookup = df_financials.set_index('symbol').to_dict('index') if not df_financials.empty else {}
    
    for symbol, symbol_data in module_data.items():
        try:
            # specialized merging logic
            row = financial_lookup.get(symbol, {'symbol': symbol})
            
            # --- FLATTENING LOGIC ---
            # 1. Key Statistics (Beta, Shares, etc.)
            _flatten_dict_into_row(row, symbol_data.get('defaultKeyStatistics'), 'KeyStats_')
            
            # 2. Earnings Trend (Forward EPS)
            _calculate_forward_eps(row, symbol_data)
            
            # 3. Summary Detail (Yield, Prices)
            _flatten_dict_into_row(row, symbol_data.get('summaryDetail'), 'Summary_')
            
            # 4. Financial Data (Targets, Margins - Yahoo's Analysis)
            _flatten_dict_into_row(row, symbol_data.get('financialData'), 'FinData_')
            
            # 5. Calendar Events (Earnings Date)
            _extract_calendar_events(row, symbol_data.get('calendarEvents'))
            
            # 6. Asset Profile (Sector, Industry)
            profile = symbol_data.get('assetProfile', {})
            if isinstance(profile, dict):
                row['Sector'] = profile.get('sector')
                row['Industry'] = profile.get('industry')
            
            enriched_rows.append(row)
            
        except Exception as e:
            logger.error(f"Error merging data for {symbol}: {e}")
            enriched_rows.append({'symbol': symbol})
            
    return pd.DataFrame(enriched_rows)

def _flatten_dict_into_row(row, source_dict, prefix):
    """Helper to flatten a dictionary into the row with a prefix."""
    if isinstance(source_dict, dict):
        for k, v in source_dict.items():
            row[f"{prefix}{k}"] = v

def _calculate_forward_eps(row, symbol_data):
    """Specific logic for Forward EPS Growth."""
    try:
        earnings_trend = symbol_data.get('earningsTrend')
        key_stats = symbol_data.get('defaultKeyStatistics', {})
        
        if earnings_trend and 'trend' in earnings_trend:
            trend = earnings_trend['trend']
            next_year = next((x for x in trend if x['period'] == '+1y'), None)
            
            if next_year and 'earningsEstimate' in next_year:
                eps_next_year = next_year['earningsEstimate'].get('avg')
                trailing_eps = key_stats.get('trailingEps')
                
                if trailing_eps and eps_next_year and trailing_eps > 0:
                    row['Forward_EPS_Growth_Percent'] = ((eps_next_year - trailing_eps) / trailing_eps) * 100
    except Exception:
        pass

def _extract_calendar_events(row, calendar_data):
    """Helper for calendar events."""
    if isinstance(calendar_data, dict):
        for key, value in calendar_data.items():
            if isinstance(value, dict) and key == 'earnings':
                 if 'earningsDate' in value:
                     row['Calendar_EarningsDate'] = str(value['earningsDate'])
            else:
                row[f'Calendar_{key}'] = value

def _save_earning_dates(cached_data):
    """
    Extracts earning dates from YahooQuery modules and saves to TABLE_EARNING_DATES.
    """
    logger.info("Extracting Earning Dates for separate table...")
    earnings_dates = {}

    for symbol, symbol_data in cached_data.items():
        calendar_data = symbol_data.get('calendarEvents')
        try:
            raw_date = calendar_data['earnings']['earningsDate'][0][:10]
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            earnings_dates[symbol] = formatted_date
        except (TypeError, IndexError, KeyError, ValueError):
            pass

    if not earnings_dates:
        return

    df = pd.DataFrame(list(earnings_dates.items()), columns=['symbol', 'earnings_date'])
    
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
    """Fetch OHLCV data using BATCH API calls and save to DB."""
    context_name = "Yahoo Historical Prices"
    logger.info(f"Starting {context_name} collection (Batch Mode)...")
    
    symbols = get_filtered_symbols_with_logging(context_name)
    all_dfs = []
    
    # 1. Group symbols by required Start Date
    # This ensures we batch efficiently: All symbols needing "Full History" go in one bucket,
    # all symbols needing "Since Yesterday" go in another.
    files_by_start_date = {} # Key: date or None, Value: list of symbols
    
    logger.info("Grouping symbols by required start date...")
    for symbol in symbols:
        last_date = get_last_price_date(symbol)
        if last_date:
            start_date = last_date + timedelta(days=1)
            # Convert to date string or keep as obj for grouping
            key = start_date.date() if isinstance(start_date, datetime) else start_date
        else:
            key = "FULL"
            
        if key not in files_by_start_date:
            files_by_start_date[key] = []
        files_by_start_date[key].append(symbol)

    # 2. Process each group in Batches
    BATCH_SIZE = 100
    
    for start_key, batch_symbols in files_by_start_date.items():
        logger.info(f"Processing group '{start_key}' with {len(batch_symbols)} symbols")
        
        # Chunking
        for i in range(0, len(batch_symbols), BATCH_SIZE):
            chunk = batch_symbols[i:i + BATCH_SIZE]
            logger.info(f"Fetching batch {i//BATCH_SIZE + 1} ({len(chunk)} symbols)...")
            
            try:
                # Setup Ticker with list
                ticker = Ticker(chunk, asynchronous=True, retry=5)
                
                # Determine parameters
                if start_key == "FULL":
                    df = ticker.history(period=YAHOO_HISTORY_PERIOD, interval=YAHOO_HISTORY_INTERVAL)
                else:
                    # start_key is a date object
                    df = ticker.history(start=start_key, interval=YAHOO_HISTORY_INTERVAL)
                
                if isinstance(df, dict) or df.empty:
                    logger.warning(f"Batch returned empty/dict: {type(df)}")
                    continue
                
                # Result from batch history is usually MultiIndex (symbol, date)
                # Reset index to make 'symbol' and 'date' columns
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
                
                if not final_cols:
                    logger.warning("No valid columns found in batch result")
                    continue
                    
                all_dfs.append(df[final_cols])
                
            except Exception as e:
                logger.error(f"Error fetching batch for group {start_key}: {e}", exc_info=True)
                continue

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        
        # [TODO: DB DEVELOPER]
        # Implement logic to save 'final_df' to the 'StockPrice' table.
        # Ensure efficient bulk insertion and handling of duplicates if necessary.
        
        logger.info(f"[Mock] Processed {len(final_df)} price rows (DB save pending implementation)")
    else:
        logger.warning("No price data collected.")

def fetch_dividends():
    """Fetch Dividend data using BATCH API calls and save to DB."""
    context_name = "Yahoo Dividends"
    logger.info(f"Starting {context_name} collection (Batch Mode)...")
    
    symbols_to_check = []
    
    # 1. Filter symbols (Optimization check)
    all_symbols = get_filtered_symbols_with_logging(context_name)
    for symbol in all_symbols:
        if should_fetch_dividends(symbol):
            symbols_to_check.append(symbol)
            
    if not symbols_to_check:
        logger.info("No symbols need dividend updates.")
        return

    # 2. Group by Start Date (Logic similar to prices)
    files_by_start_date = {} 
    
    for symbol in symbols_to_check:
        last_date = get_last_dividend_date(symbol)
        if last_date:
            start_date = last_date + timedelta(days=1)
            key = start_date.date() if isinstance(start_date, datetime) else start_date
        else:
            key = "FULL"
            
        if key not in files_by_start_date:
            files_by_start_date[key] = []
        files_by_start_date[key].append(symbol)
        
    all_dfs = []
    BATCH_SIZE = 100
    
    for start_key, batch_symbols in files_by_start_date.items():
        logger.info(f"Processing Dividends group '{start_key}' with {len(batch_symbols)} symbols")
        
        for i in range(0, len(batch_symbols), BATCH_SIZE):
            chunk = batch_symbols[i:i + BATCH_SIZE]
            
            try:
                ticker = Ticker(chunk, asynchronous=True, retry=5)
                
                if start_key == "FULL":
                    # Use period='max' or configured history for dividends to be safe
                    # 'max' is best for dividends to ensure we get everything if table is empty
                    df = ticker.history(period=YAHOO_HISTORY_PERIOD, interval='1d')
                else:
                    df = ticker.history(start=start_key, interval='1d')
                    
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
                logger.error(f"Error fetching dividend batch: {e}", exc_info=True)
                continue

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        
        # [TODO: DB DEVELOPER]
        # Implement logic to save 'final_df' to the 'Dividends' table.
        
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
