import pandas as pd
import numpy as np
import time
import sys
import os

from src.database import insert_into_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import get_filtered_symbols_with_logging
from yahooquery import Ticker


def prepare_fundamentals_for_merge_v2(df_fundamentals):
    """
    Process fundamentals from multiple yahooquery endpoints.
    Works with the new comprehensive data structure that includes MarketCap.
    """
    print(f"Available fundamental columns: {list(df_fundamentals.columns)}")
    
    # Make a copy for processing
    df_processed = df_fundamentals.copy()
    
    # Calculate additional ratios using available data
    if 'MarketCap' in df_processed.columns and 'NetIncome' in df_processed.columns:
        df_processed['PE_Ratio_Calc'] = np.where(
            (df_processed['NetIncome'] > 0) & (df_processed['MarketCap'] > 0),
            df_processed['MarketCap'] / df_processed['NetIncome'], np.nan)
        print("✅ Calculated PE_Ratio_Calc using MarketCap and NetIncome")
    else:
        print("⚠️  Cannot calculate PE_Ratio_Calc - MarketCap or NetIncome not available")
        df_processed['PE_Ratio_Calc'] = np.nan
    
    if 'MarketCap' in df_processed.columns and 'TotalRevenue' in df_processed.columns:
        df_processed['PS_Ratio'] = np.where(
            (df_processed['TotalRevenue'] > 0) & (df_processed['MarketCap'] > 0),
            df_processed['MarketCap'] / df_processed['TotalRevenue'], np.nan)
        print("✅ Calculated PS_Ratio using MarketCap and TotalRevenue")
    else:
        print("⚠️  Cannot calculate PS_Ratio - MarketCap or TotalRevenue not available")
        df_processed['PS_Ratio'] = np.nan
    
    if 'TotalDebt' in df_processed.columns and 'MarketCap' in df_processed.columns:
        df_processed['DebtToMarketCap'] = np.where(
            (df_processed['MarketCap'] > 0),
            df_processed['TotalDebt'] / df_processed['MarketCap'], np.nan)
        print("✅ Calculated DebtToMarketCap ratio")
    else:
        print("⚠️  Cannot calculate DebtToMarketCap - TotalDebt or MarketCap not available")
        df_processed['DebtToMarketCap'] = np.nan
    
    if 'EBITDA' in df_processed.columns and 'MarketCap' in df_processed.columns:
        df_processed['EV_EBITDA_Approx'] = np.where(
            (df_processed['EBITDA'] > 0) & (df_processed['MarketCap'] > 0),
            df_processed['MarketCap'] / df_processed['EBITDA'], np.nan)  # Simplified without net debt
        print("✅ Calculated EV/EBITDA approximation")
    else:
        print("⚠️  Cannot calculate EV/EBITDA - EBITDA or MarketCap not available")
        df_processed['EV_EBITDA_Approx'] = np.nan
    
    # Clean up any NaN-only columns
    for col in df_processed.columns:
        if df_processed[col].isna().all():
            print(f"⚠️  Column '{col}' is all NaN - keeping for structure consistency")
    
    print(f"Processed fundamentals: {df_processed.shape} with {len(df_processed.columns)} columns")
    return df_processed


def prepare_fundamentals_for_merge(df_full_fundamentals):
    """
    LEGACY FUNCTION - kept for backward compatibility
    Select essential fundamentals and calculate ratios. 
    Reduces from 238 columns to ~28 key metrics.
    """
    # ESSENTIAL RAW FUNDAMENTALS
    essential_columns = {
        'MarketCap': 'MarketCap', 'EnterpriseValue': 'EnterpriseValue',
        'TotalRevenue': 'TotalRevenue', 'TotalAssets': 'TotalAssets',
        'NetIncome': 'NetIncome', 'EBITDA': 'EBITDA',
        'FreeCashFlow': 'FreeCashFlow', 'OperatingCashFlow': 'OperatingCashFlow',
        'StockholdersEquity': 'StockholdersEquity', 'TotalDebt': 'TotalDebt',
        'CurrentAssets': 'CurrentAssets', 'CurrentLiabilities': 'CurrentLiabilities',
        'TangibleBookValue': 'TangibleBookValue', 'OrdinarySharesNumber': 'OrdinarySharesNumber',
        'BasicEPS': 'BasicEPS', 'DilutedEPS': 'DilutedEPS',
        'CashDividendsPaid': 'CashDividendsPaid',
        'symbol': 'symbol', 'periodType': 'periodType'
    }
    
    # Select available columns
    available_columns = {k: v for k, v in essential_columns.items() 
                        if v in df_full_fundamentals.columns}
    
    print(f"Available fundamental columns: {list(available_columns.keys())}")
    print(f"Missing columns: {set(essential_columns.keys()) - set(available_columns.keys())}")
    
    df_selected = df_full_fundamentals[[col for col in available_columns.values()]].copy()
    
    # Calculate ratios only if required columns are available
    if 'MarketCap' in df_selected.columns and 'NetIncome' in df_selected.columns:
        df_selected['PE_Ratio'] = np.where(
            (df_selected['NetIncome'] > 0) & (df_selected['MarketCap'] > 0),
            df_selected['MarketCap'] / df_selected['NetIncome'], np.nan)
    else:
        print("Warning: Cannot calculate PE_Ratio - MarketCap or NetIncome not available")
        df_selected['PE_Ratio'] = np.nan
    
    if 'MarketCap' in df_selected.columns and 'TangibleBookValue' in df_selected.columns:
        df_selected['PB_Ratio'] = np.where(
            (df_selected['TangibleBookValue'] > 0) & (df_selected['MarketCap'] > 0),
            df_selected['MarketCap'] / df_selected['TangibleBookValue'], np.nan)
    else:
        print("Warning: Cannot calculate PB_Ratio - MarketCap or TangibleBookValue not available")
        df_selected['PB_Ratio'] = np.nan
    
    if 'StockholdersEquity' in df_selected.columns and 'TotalDebt' in df_selected.columns:
        df_selected['DebtEquity_Ratio'] = np.where(
            (df_selected['StockholdersEquity'] > 0) & (df_selected['TotalDebt'] >= 0),
            df_selected['TotalDebt'] / df_selected['StockholdersEquity'], np.nan)
    else:
        print("Warning: Cannot calculate DebtEquity_Ratio - StockholdersEquity or TotalDebt not available")
        df_selected['DebtEquity_Ratio'] = np.nan
    
    if 'StockholdersEquity' in df_selected.columns and 'NetIncome' in df_selected.columns:
        df_selected['ROE_Fund'] = np.where(
            (df_selected['StockholdersEquity'] > 0),
            df_selected['NetIncome'] / df_selected['StockholdersEquity'], np.nan)
    else:
        print("Warning: Cannot calculate ROE_Fund - StockholdersEquity or NetIncome not available")
        df_selected['ROE_Fund'] = np.nan
    
    if 'TotalAssets' in df_selected.columns and 'NetIncome' in df_selected.columns:
        df_selected['ROA'] = np.where(
            (df_selected['TotalAssets'] > 0),
            df_selected['NetIncome'] / df_selected['TotalAssets'], np.nan)
    else:
        print("Warning: Cannot calculate ROA - TotalAssets or NetIncome not available")
        df_selected['ROA'] = np.nan
    
    if 'MarketCap' in df_selected.columns and 'CashDividendsPaid' in df_selected.columns:
        df_selected['DividendYield_Calc'] = np.where(
            (df_selected['MarketCap'] > 0) & (df_selected['CashDividendsPaid'] < 0),
            abs(df_selected['CashDividendsPaid']) / df_selected['MarketCap'], np.nan)
    else:
        print("Warning: Cannot calculate DividendYield_Calc - MarketCap or CashDividendsPaid not available")
        df_selected['DividendYield_Calc'] = np.nan
    
    # Get latest data per symbol
    if 'annual' in df_selected['periodType'].values:
        annual_data = df_selected[df_selected['periodType'] == 'annual']
        latest_data = annual_data.groupby('symbol').last().reset_index()
    else:
        latest_data = df_selected.groupby('symbol').last().reset_index()
    
    # Drop meta columns
    final_columns = [col for col in latest_data.columns if col != 'periodType']
    return latest_data[final_columns]


def get_yahooquery_financials():
    # Use centralized config validation instead of testmode parameter
    symbols_to_use = get_filtered_symbols_with_logging("Yahoo Financials")
    
    tickers = Ticker(symbols_to_use, asynchronous=True)

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

def generate_fundamental_data():
    """
    Main function to generate fundamental data - called from main.py
    Uses ALL available yahooquery endpoints to get COMPLETE fundamentals (200+ columns)
    """
    # Test mode logic and logging centrally from config
    symbols = get_filtered_symbols_with_logging("Yahoo Fundamentals")
    
    print("Processing fundamentals: collecting ALL available metrics from multiple endpoints...")
    
    # Method 1: Get ALL financial data using all_financial_data (200+ columns)
    print("Fetching comprehensive financial data using all_financial_data()...")
    tickers = Ticker(symbols, asynchronous=True)
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
    
    for symbol in symbols:
        try:
            print(f"Enhancing data for {symbol} with additional endpoints...")
            ticker = Ticker(symbol)
            
            # Start with financial data if available
            if symbol in df_financial_latest['symbol'].values:
                symbol_data = df_financial_latest[df_financial_latest['symbol'] == symbol].iloc[0].to_dict()
            else:
                symbol_data = {'symbol': symbol}
            
            # Add KEY_STATS data
            try:
                key_stats = ticker.key_stats
                if symbol in key_stats and isinstance(key_stats[symbol], dict):
                    stats = key_stats[symbol]
                    # Add all key_stats with prefix to avoid conflicts
                    for key, value in stats.items():
                        symbol_data[f'KeyStats_{key}'] = value
                    
                    # Calculate Forward EPS Growth using earnings_trend
                    try:
                        earnings_trend = ticker.earnings_trend
                        if symbol in earnings_trend and 'trend' in earnings_trend[symbol]:
                            trend = earnings_trend[symbol]['trend']
                            next_year = next((x for x in trend if x['period'] == '+1y'), None)
                            if next_year and 'earningsEstimate' in next_year:
                                eps_next_year = next_year['earningsEstimate'].get('avg')
                                trailing_eps = stats.get('trailingEps')
                                
                                if trailing_eps and eps_next_year and trailing_eps > 0:
                                    symbol_data['Forward_EPS_Growth_Percent'] = ((eps_next_year - trailing_eps) / trailing_eps) * 100
                    except Exception as e:
                        print(f"  Warning: Could not get EPS growth for {symbol}: {e}")
            except Exception as e:
                print(f"  Warning: Could not get key_stats for {symbol}: {e}")
            
            # Add SUMMARY_DETAIL data  
            try:
                summary_detail = ticker.summary_detail
                if symbol in summary_detail and isinstance(summary_detail[symbol], dict):
                    summary = summary_detail[symbol]
                    # Add all summary_detail with prefix to avoid conflicts
                    for key, value in summary.items():
                        symbol_data[f'Summary_{key}'] = value
            except Exception as e:
                print(f"  Warning: Could not get summary_detail for {symbol}: {e}")
            
            # Add FINANCIAL_DATA 
            try:
                financial_data = ticker.financial_data
                if symbol in financial_data and isinstance(financial_data[symbol], dict):
                    fin_data = financial_data[symbol]
                    # Add all financial_data with prefix to avoid conflicts
                    for key, value in fin_data.items():
                        symbol_data[f'FinData_{key}'] = value
            except Exception as e:
                print(f"  Warning: Could not get financial_data for {symbol}: {e}")
            
            all_fundamental_data.append(symbol_data)
            
        except Exception as e:
            print(f"Error enhancing data for {symbol}: {e}")
            # Add minimal data for failed symbols
            all_fundamental_data.append({'symbol': symbol})
        
        time.sleep(0.3)  # Rate limiting
    
    if not all_fundamental_data:
        print("No fundamental data collected")
        return
    
    # Create comprehensive DataFrame from all collected data
    df_all_fundamentals = pd.DataFrame(all_fundamental_data)
    
    print(f"✅ Final dataset: {df_all_fundamentals.shape} with {df_all_fundamentals.shape[1]} total columns")
    print(f"   Columns include: financial_data, key_stats, summary_detail, financial_data endpoints")
    
    # Save full raw data (ALL columns)
    df_all_fundamentals.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER)
    print(f"Full fundamentals saved: {PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER}")
    
    # Process for essential metrics (for UI display)
    df_processed = prepare_fundamentals_for_merge_v2(df_all_fundamentals)
    
    # Save processed data (essential columns for display)
    df_processed.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_PROCESSED_FEATHER)
    print(f"Processed fundamentals saved: {PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_PROCESSED_FEATHER}")
    print(f"Ready for merge: {df_processed.shape} ({df_processed.shape[1]} display columns)")
    print(f"Available for filtering: {df_all_fundamentals.shape[1]} total columns")

    # --- Database Persistence ---
    insert_into_table(
        table_name=TABLE_FUNDAMENTAL_DATA_YAHOO,
        dataframe=df_all_fundamentals,
        if_exists="replace"
    )
    insert_into_table(
        table_name=TABLE_FUNDAMENTAL_DATA_YAHOO_PROCESSED,
        dataframe=df_processed,
        if_exists="replace"
    )
    
if __name__ == "__main__":

    start = time.time()
    get_yahooquery_financials()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")
