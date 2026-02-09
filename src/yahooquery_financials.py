import logging
import time
import sys
import os
import numpy as np
import pandas as pd

from config import TABLE_FUNDAMENTAL_DATA_YAHOO, TABLE_STOCK_PRICES_YAHOO
from src.database import get_postgres_engine, insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper
from config_utils import get_filtered_symbols_with_logging

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        
        print(f"✅ Collected {df_financial_latest.shape[1]} columns from all_financial_data")
    else:
        # Fallback: create empty dataframe with symbol column
        df_financial_latest = pd.DataFrame({'symbol': symbols})
        print("⚠️  all_financial_data returned empty - using fallback")
    
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

    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_FUNDAMENTAL_DATA_YAHOO)
        insert_into_table(
            connection,
            table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
            dataframe=df_all_fundamentals,
            if_exists="append"
        )

def load_stock_day_prices():
    logger.info("Fetching day stock prices (high, low, close) using YahooQueryScraper...")
    yahoo_query = YahooQueryScraper.instance()
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
                

if __name__ == "__main__":

    start = time.time()
    generate_fundamental_data()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")
