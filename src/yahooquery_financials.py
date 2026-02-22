import logging
import time
import sys
import os
import numpy as np
import pandas as pd

from config import TABLE_FUNDAMENTAL_DATA_YAHOO, TABLE_STOCK_PRICES_YAHOO
from src.database import get_postgres_engine, insert_into_table, insert_into_table_bulk, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

def generate_fundamental_data(symbols):

    """
    Main function to generate fundamental data - called from main.py
    Uses ALL available yahooquery endpoints to get COMPLETE fundamentals (200+ columns)
    
    Args:
        enable_diagnostics (bool): If True, enables detailed column analysis logging
                                 If False, runs normal processing without diagnostic output
    """

    logger.info("Processing fundamentals: collecting ALL available metrics from multiple endpoints...")


    # Method 1: Get ALL financial data using all_financial_data (200+ columns)
    logger.info("Fetching comprehensive financial data using all_financial_data()...")
    yahoo_query = YahooQueryScraper.instance(symbols)
    local_batch_size = 500
    local_symbol_batches = [symbols[i:i + local_batch_size] for i in range(0, len(symbols), local_batch_size)]
    
    batch = 1
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_FUNDAMENTAL_DATA_YAHOO)
        for symbol_batch in local_symbol_batches:
            df_all_financial = None
            data = None
            logger.info(f"Batch {batch}/{len(local_symbol_batches)} symbols {len(symbol_batch)}")
            df_all_financial = yahoo_query.get_all_financial_data(symbols=symbol_batch)
            data = yahoo_query.get_modules(symbols=symbol_batch, modules='financialData defaultKeyStatistics earningsTrend summaryDetail', ignore_cache=True)

            if df_all_financial is not None and not df_all_financial.empty:
                # Get latest data per symbol
                if 'asOfDate' in df_all_financial.columns:
                    df_all_financial['asOfDate'] = pd.to_datetime(df_all_financial['asOfDate'])
                    idx = df_all_financial.groupby('symbol')['asOfDate'].idxmax()
                    df_financial_latest = df_all_financial.loc[idx].reset_index(drop=True)
                else:
                    df_financial_latest = df_all_financial.groupby('symbol').last().reset_index()
                
                logger.info(f"✅ Collected {df_financial_latest.shape[1]} columns from all_financial_data")
            else:
                # Fallback: create empty dataframe with symbol column
                df_financial_latest = pd.DataFrame({'symbol': symbols})
                logger.info("⚠️  all_financial_data returned empty - using fallback")
            
            # Method 2: Add additional data from specific endpoints for completeness
            all_fundamental_data = []
            

            for symbol, symbol_data in data.items():
                try:
                    # Start with financial data if available
                    if symbol in df_financial_latest['symbol'].values:
                        symbol_dict = df_financial_latest[df_financial_latest['symbol'] == symbol].iloc[0].to_dict()
                    else:
                        # symbol_dict = {'symbol': symbol}
                        continue # Skip symbols that don't have financial data
                    
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
                    
                    all_fundamental_data.append(symbol_dict)
                    
                except Exception as e:
                    logger.error(f"Error processing data for {symbol}: {e}")
                    all_fundamental_data.append({'symbol': symbol})
            
            if all_fundamental_data is None or len(all_fundamental_data) == 0:
                logger.warning("No fundamental data collected")
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
                connection,
                table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
                dataframe=df_all_fundamentals,
                if_exists="append"
            )
            batch +=1

def generate_fundamental_data_oom(symbols):

    """
    Main function to generate fundamental data - called from main.py
    Uses ALL available yahooquery endpoints to get COMPLETE fundamentals (200+ columns)
    
    Args:
        enable_diagnostics (bool): If True, enables detailed column analysis logging
                                 If False, runs normal processing without diagnostic output
    """

    logger.info("Processing fundamentals: collecting ALL available metrics from multiple endpoints...")


    # Method 1: Get ALL financial data using all_financial_data (200+ columns)
    logger.info("Fetching comprehensive financial data using all_financial_data()...")
    yahoo_query = YahooQueryScraper.instance(symbols)
    df_all_financial_full = yahoo_query.get_all_financial_data()
    data = yahoo_query.get_modules()

    df_all_financial_batches = np.array_split(df_all_financial_full, 200) if df_all_financial_full is not None and not df_all_financial_full.empty else []
    logger.info(f"Fetched all_financial_data with {len(df_all_financial_batches)} batches (total {len(df_all_financial_full) if df_all_financial_full is not None else 0} rows)")
    
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_FUNDAMENTAL_DATA_YAHOO)
        for i, df_all_financial in enumerate(df_all_financial_batches):
            logger.info(f"Processing batch {i+1}/{len(df_all_financial_batches)} with {len(df_all_financial) if df_all_financial is not None else 0} rows")

            if df_all_financial is not None and not df_all_financial.empty:
                # Get latest data per symbol
                if 'asOfDate' in df_all_financial.columns:
                    df_all_financial['asOfDate'] = pd.to_datetime(df_all_financial['asOfDate'])
                    idx = df_all_financial.groupby('symbol')['asOfDate'].idxmax()
                    df_financial_latest = df_all_financial.loc[idx].reset_index(drop=True)
                else:
                    df_financial_latest = df_all_financial.groupby('symbol').last().reset_index()
                
                logger.info(f"✅ Collected {df_financial_latest.shape[1]} columns from all_financial_data")
            else:
                # Fallback: create empty dataframe with symbol column
                df_financial_latest = pd.DataFrame({'symbol': symbols})
                logger.info("⚠️  all_financial_data returned empty - using fallback")
            
            # Method 2: Add additional data from specific endpoints for completeness
            all_fundamental_data = []
            

            for symbol, symbol_data in data.items():
                try:
                    # Start with financial data if available
                    if symbol in df_financial_latest['symbol'].values:
                        symbol_dict = df_financial_latest[df_financial_latest['symbol'] == symbol].iloc[0].to_dict()
                    else:
                        # symbol_dict = {'symbol': symbol}
                        continue # Skip symbols that don't have financial data
                    
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
                    
                    all_fundamental_data.append(symbol_dict)
                    
                except Exception as e:
                    logger.error(f"Error processing data for {symbol}: {e}")
                    all_fundamental_data.append({'symbol': symbol})
            
            if all_fundamental_data is None or len(all_fundamental_data) == 0:
                logger.warning("No fundamental data collected")
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
                connection,
                table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
                dataframe=df_all_fundamentals,
                if_exists="append"
            )

def load_stock_prices(symbols):
    logger.info("Fetching day stock prices (high, low, close) using YahooQueryScraper...")
    yahoo_query = YahooQueryScraper.instance(symbols)
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_PRICES_YAHOO)
        for df in yahoo_query.get_historical_prices(period='1d'):
            if df is not None and not df.empty:
                # drop date column
                if 'date' in df.columns:
                    df = df.drop(columns=['date'])
                    insert_into_table(
                        connection,
                        TABLE_STOCK_PRICES_YAHOO,
                        df,
                        if_exists="append"
                    )

def load_historical_prices_(symbols):
    yahoo_query = YahooQueryScraper.instance(symbols)
    for df in yahoo_query.get_historical_prices(period='26y'):
        if df is not None and not df.empty:
            # rename date column to snapshot_date for consistency
            if 'date' in df.columns:
                df = df.rename(columns={'date': 'snapshot_date'})
            with get_postgres_engine().begin() as connection:
                insert_into_table(
                    connection, 
                    f"{TABLE_STOCK_PRICES_YAHOO}HistoryDaily", 
                    df, 
                    if_exists="append"
                )

def load_historical_prices(symbols):
    logger.info("Fetching historical stock prices (high, low, close) using YahooQueryScraper...")
    table_name = f"{TABLE_STOCK_PRICES_YAHOO}HistoryDaily"
    yahoo_query = YahooQueryScraper.instance(symbols)
    total_rows = 0
    conn = get_postgres_engine().raw_connection()
    try:
        truncate_table(conn, table_name)

        batch = 1
        for df in yahoo_query.get_historical_prices(period='26y'):
            logger.info(f"Batch {batch} - fetched {len(df) if df is not None else 0} historical price entries")
            if df is not None and not df.empty:
                # rename date column to snapshot_date for consistency
                df = df.rename(columns={'date': 'snapshot_date'})
                # df = df.astype({'volume':'int'})
                df['volume'] = df['volume'].fillna(0).astype(int)
                insert_into_table_bulk(
                    conn, 
                    table_name, 
                    df, 
                    if_exists="append"
                )
                total_rows += len(df)
            batch += 1

        conn.commit()
    finally:
        conn.close()
    logger.info(f"Total historical price entries loaded: {total_rows}")

if __name__ == "__main__":

    start = time.time()
    generate_fundamental_data()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")
