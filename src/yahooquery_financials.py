import pandas as pd
import numpy as np
import time
import sys
import os

from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import get_filtered_symbols_with_logging
from yahooquery import Ticker


def prepare_fundamentals_for_merge(df_fundamentals):
    """
    Process fundamentals from multiple yahooquery endpoints.
    Works with the new comprehensive data structure that includes MarketCap.
    """
    print(f"Available fundamental columns: {len(df_fundamentals.columns)}")
    
    df_processed = df_fundamentals.copy()
    
    if 'MarketCap' in df_processed.columns and 'NetIncome' in df_processed.columns:
        df_processed['PE_Ratio_Calc'] = np.where(
            (df_processed['NetIncome'] > 0) & (df_processed['MarketCap'] > 0),
            df_processed['MarketCap'] / df_processed['NetIncome'], np.nan)
        print("Calculated PE_Ratio_Calc using MarketCap and NetIncome")
    else:
        print("Cannot calculate PE_Ratio_Calc - MarketCap or NetIncome not available")
        df_processed['PE_Ratio_Calc'] = np.nan
    
    if 'MarketCap' in df_processed.columns and 'TotalRevenue' in df_processed.columns:
        df_processed['PS_Ratio'] = np.where(
            (df_processed['TotalRevenue'] > 0) & (df_processed['MarketCap'] > 0),
            df_processed['MarketCap'] / df_processed['TotalRevenue'], np.nan)
        print("Calculated PS_Ratio using MarketCap and TotalRevenue")
    else:
        print("Cannot calculate PS_Ratio - MarketCap or TotalRevenue not available")
        df_processed['PS_Ratio'] = np.nan
    
    if 'TotalDebt' in df_processed.columns and 'MarketCap' in df_processed.columns:
        df_processed['DebtToMarketCap'] = np.where(
            (df_processed['MarketCap'] > 0),
            df_processed['TotalDebt'] / df_processed['MarketCap'], np.nan)
        print("Calculated DebtToMarketCap ratio")
    else:
        print("Cannot calculate DebtToMarketCap - TotalDebt or MarketCap not available")
        df_processed['DebtToMarketCap'] = np.nan
    
    if 'EBITDA' in df_processed.columns and 'MarketCap' in df_processed.columns:
        df_processed['EV_EBITDA_Approx'] = np.where(
            (df_processed['EBITDA'] > 0) & (df_processed['MarketCap'] > 0),
            df_processed['MarketCap'] / df_processed['EBITDA'], np.nan)
        print("Calculated EV/EBITDA approximation")
    else:
        print("Cannot calculate EV/EBITDA - EBITDA or MarketCap not available")
        df_processed['EV_EBITDA_Approx'] = np.nan
    
    for col in df_processed.columns:
        if df_processed[col].isna().all():
            print(f"Column '{col}' is all NaN - keeping for structure consistency")
    
    print(f"Processed fundamentals: {df_processed.shape} with {len(df_processed.columns)} columns")
    return df_processed



def get_yahooquery_financials():
    # Use centralized config validation instead of testmode parameter
    symbols_to_use = get_filtered_symbols_with_logging("Yahoo Financials")
    
    tickers = Ticker(symbols_to_use)

    # request data
    df = tickers.all_financial_data()

    # symbol as column not index
    df.reset_index(inplace=True)

    # ensure asOfDate is a datetime type
    df['asOfDate'] = pd.to_datetime(df['asOfDate'])

    # find index of the most recent row per symbol
    idx = df.groupby('symbol')['asOfDate'].idxmax()

    # create filtered DataFrame with all raw data
    df_full = df.loc[idx].reset_index(drop=True)

    # NEW: Prepare essential fundamentals + calculated ratios (238 → 28 columns)
    print("Processing fundamentals: selecting essential metrics and calculating ratios...")
    df_processed = prepare_fundamentals_for_merge(df_full)

    # store full dataframe (for reference/debugging)
    df_full.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER)
    df_full.to_csv('yahooquery_financial.csv', sep=';', decimal=',', index=False)
    
    # NEW: Store processed fundamentals (for merging)
    processed_path = PATH_DATA / 'yahooquery_financial_processed.feather'
    df_processed.to_feather(processed_path)
    df_processed.to_csv('yahooquery_financial_processed.csv', sep=';', decimal=',', index=False)
    
    print(f"Full fundamentals saved: {PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER}")
    print(f"Processed fundamentals saved: {processed_path}")
    print(f"Ready for merge: {df_processed.shape} ({len(df_processed.columns)} columns)")
    
    return df_processed

def generate_fundamental_data(enable_diagnostics=False):

    """
    Main function to generate fundamental data - called from main.py
    Uses ALL available yahooquery endpoints to get COMPLETE fundamentals (200+ columns)
    
    Args:
        enable_diagnostics (bool): If True, enables detailed column analysis logging
                                 If False, runs normal processing without diagnostic output
    """
    # Test mode logic and logging centrally from config
    symbols = get_filtered_symbols_with_logging("Yahoo Fundamentals")
    
    print("Processing fundamentals: collecting ALL available metrics from multiple endpoints...")
    
    # Method 1: Get ALL financial data using all_financial_data (200+ columns)
    print("Fetching comprehensive financial data using all_financial_data()...")
    tickers = Ticker(symbols)
    df_all_financial = tickers.all_financial_data()
    
    if df_all_financial is not None and not df_all_financial.empty:
        # Reset index to make symbol a column
        df_all_financial.reset_index(inplace=True)
        
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
    
    key_stats_all = tickers.key_stats
    summary_detail_all = tickers.summary_detail
    financial_data_all = tickers.financial_data
    earnings_trend_all = tickers.earnings_trend

    for symbol in symbols:
        try:
            print(f"Enhancing data for {symbol} with additional endpoints...")
            # ticker = Ticker(symbol)
            
            # Start with financial data if available
            if symbol in df_financial_latest['symbol'].values:
                symbol_data = df_financial_latest[df_financial_latest['symbol'] == symbol].iloc[0].to_dict()
            else:
                symbol_data = {'symbol': symbol}
            
            # Add KEY_STATS data
            try:
                key_stats = key_stats_all[symbol]
                if symbol in key_stats and isinstance(key_stats[symbol], dict):
                    stats = key_stats[symbol]
                    # Add all key_stats with prefix to avoid conflicts
                    for key, value in stats.items():
                        symbol_data[f'KeyStats_{key}'] = value
                    
                    # Calculate Forward EPS Growth using earnings_trend
                    try:
                        earnings_trend = earnings_trend_all[symbol]
                        if symbol in earnings_trend and 'trend' in earnings_trend[symbol]:
                            trend = earnings_trend[symbol]['trend']
                            next_year = next((x for x in trend if x['period'] == '+1y'), None)
                            if next_year and 'earningsEstimate' in next_year:
                                eps_next_year = next_year['earningsEstimate'].get('avg')
                                trailing_eps = stats.get('trailingEps')
                                
                                if trailing_eps and eps_next_year and trailing_eps > 0:
                                    symbol_data['Forward_EPS_Growth_Percent'] = ((eps_next_year - trailing_eps) / trailing_eps) * 100
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Add SUMMARY_DETAIL data  
            try:
                summary_detail = summary_detail_all[symbol]
                if symbol in summary_detail and isinstance(summary_detail[symbol], dict):
                    summary = summary_detail[symbol]
                    # Add all summary_detail with prefix to avoid conflicts
                    for key, value in summary.items():
                        symbol_data[f'Summary_{key}'] = value
            except Exception:
                pass
            
            # Add FINANCIAL_DATA 
            try:
                financial_data = financial_data_all[symbol]
                if symbol in financial_data and isinstance(financial_data[symbol], dict):
                    fin_data = financial_data[symbol]
                    # Add all financial_data with prefix to avoid conflicts
                    for key, value in fin_data.items():
                        symbol_data[f'FinData_{key}'] = value
            except Exception:
                pass
            
            all_fundamental_data.append(symbol_data)
            
        except Exception:
            all_fundamental_data.append({'symbol': symbol})
        
        # time.sleep(0.3)  # Rate limiting
    
    if not all_fundamental_data:
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

    try:
        df_all_fundamentals.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER)
    except Exception:
        csv_path = PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER.with_suffix('.csv')
        df_all_fundamentals.to_csv(csv_path, index=False)
        return

    df_processed = prepare_fundamentals_for_merge(df_all_fundamentals)
    df_processed.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_PROCESSED_FEATHER)

    truncate_table(TABLE_FUNDAMENTAL_DATA_YAHOO)
    insert_into_table(
        table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
        dataframe=df_all_fundamentals,
        if_exists="append"
    )
    truncate_table(TABLE_FUNDAMENTAL_DATA_YAHOO_PROCESSED)
    insert_into_table(
        table_name=TABLE_FUNDAMENTAL_DATA_YAHOO_PROCESSED,
        dataframe=df_processed,
        if_exists="append"
    )

def generate_fundamental_data2(enable_diagnostics=False):

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

    try:
        df_all_fundamentals.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER)
    except Exception:
        csv_path = PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER.with_suffix('.csv')
        df_all_fundamentals.to_csv(csv_path, index=False)
        return

    truncate_table(TABLE_FUNDAMENTAL_DATA_YAHOO)
    insert_into_table(
        table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
        dataframe=df_all_fundamentals,
        if_exists="append"
    )

if __name__ == "__main__":

    start = time.time()
    get_yahooquery_financials()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")
