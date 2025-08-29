import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.live_stock_price_collector import fetch_current_prices


def merge_data_dataframes():
    # Merge Option Data and Price/Indicator Data
    print("Merging Option Data and Price/Indicator Data")
    df_option_data = pd.read_feather(PATH_DATAFRAME_OPTION_DATA_FEATHER)
    df_price_indicators = pd.read_feather(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER)
    df_merged = pd.merge(df_option_data, df_price_indicators, how='left', on='symbol')

    # Join Yahoo Finance Analyst Price Targets
    print("Joining Yahoo Finance Analyst Price Targets")
    df_price_targets = pd.read_feather(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER)
    df_merged = pd.merge(df_merged, df_price_targets, how='left', on='symbol')

    # Join Dividend File Data
    print("Joining Dividend File Data")
    df_dividend_data = pd.read_feather(PATH_DIVIDEND_RADAR)
    print("Dividend columns:", df_dividend_data.columns.tolist())
    print("Has Classification?", 'Classification' in df_dividend_data.columns)
    df_merged = pd.merge(df_merged, df_dividend_data, how='left', left_on='symbol', right_on='Symbol')

    # Join Earning Dates
    print("Joining Earning Dates")
    df_earning_dates = pd.read_feather(PATH_DATAFRAME_EARNING_DATES_FEATHER)
    df_merged = pd.merge(df_merged, df_earning_dates, how='left', left_on='symbol', right_on='symbol')

    # Join Yahoo Option Chain
    print("Joining Yahoo Option Chain")
    df_yahooquery_option_chain = pd.read_feather(PATH_DATAFRAME_YAHOOQUERY_OPTION_CHAIN_FEATHER, columns=['contractSymbol', 'option_volume', 'option_open_interest'])
    df_merged = pd.merge(df_merged, df_yahooquery_option_chain, how='left', left_on='option_osi', right_on='contractSymbol')

    # NEW: Join Yahoo Fundamentals (processed)
    print("Joining Yahoo Fundamentals")
    try:
        fundamentals_path = PATH_DATA / 'yahooquery_financial_processed.feather'
        df_fundamentals = pd.read_feather(fundamentals_path)
        print(f"Loaded fundamentals: {df_fundamentals.shape}")
        print(f"Fundamental symbols: {list(df_fundamentals['symbol'].unique())}")
        
        # Merge fundamentals
        df_merged = pd.merge(df_merged, df_fundamentals, how='left', on='symbol')
        print(f"After fundamentals merge: {df_merged.shape}")
        
    except FileNotFoundError:
        print("WARNING: Processed fundamentals not found, skipping fundamentals merge")
    except Exception as e:
        print(f"ERROR merging fundamentals: {e}")

    # Join Dividend Stability Analysis
    print("Joining Dividend Stability Analysis")
    try:
        stability_path = PATH_DATA / 'dividend_stability_analysis.feather'
        df_stability = pd.read_feather(stability_path)
        print(f"Loaded dividend stability: {df_stability.shape}")
        print(f"Stability symbols: {list(df_stability['symbol'].unique())}")
        
        # Merge stability analysis
        df_merged = pd.merge(df_merged, df_stability, how='left', on='symbol')
        print(f"After stability merge: {df_merged.shape}")
        
    except FileNotFoundError:
        print("WARNING: Dividend stability analysis not found, skipping stability merge")
    except Exception as e:
        print(f"ERROR merging dividend stability: {e}")

    # Join Live Stock Prices (fetch on-the-fly)
    print("Fetching and joining live stock prices (on-the-fly)")
    try:
        # Get unique symbols present in the merged dataframe
        symbols_for_prices = df_merged['symbol'].dropna().astype(str).unique().tolist()
        print(f"Fetching live prices for {len(symbols_for_prices)} unique symbols")

        df_live_prices = fetch_current_prices(symbols_for_prices)
        print(f"Fetched live prices: {df_live_prices.shape}")
        print(f"Live price symbols: {df_live_prices['symbol'].nunique()}")

        # Merge live prices into the main dataframe
        df_merged = pd.merge(df_merged, df_live_prices, how='left', on='symbol')
        print(f"After live prices merge: {df_merged.shape}")

    except Exception as e:
        print(f"ERROR fetching/merging live stock prices: {e}")

    # Calculate Option Pricing Columns (IntrinsicValue & ExtrinsicValue for ALL options)
    print("Calculating option pricing columns for ALL options (Calls & Puts)")
    try:
        # Convert columns to numeric for calculations
        df_merged['strike'] = pd.to_numeric(df_merged['strike'], errors='coerce')
        df_merged['live_stock_price'] = pd.to_numeric(df_merged['live_stock_price'], errors='coerce')
        df_merged['theoPrice'] = pd.to_numeric(df_merged['theoPrice'], errors='coerce')
        
        # Identify Call and Put options from option column (e.g., "AAPL250905C110.0" or "AAPL250905P110.0")
        # Extract option type from option string
        df_merged['option_type_from_symbol'] = df_merged['option'].str.extract(r'([CP])', expand=False)
        
        # Also check the 'option-type' column if it exists
        if 'option-type' in df_merged.columns:
            # Create unified option type
            df_merged['unified_option_type'] = df_merged['option-type'].fillna(df_merged['option_type_from_symbol'])
        else:
            df_merged['unified_option_type'] = df_merged['option_type_from_symbol']
        
        # Identify calls and puts
        is_call = df_merged['unified_option_type'].isin(['call', 'Call', 'CALL', 'C', 'c'])
        is_put = df_merged['unified_option_type'].isin(['put', 'Put', 'PUT', 'P', 'p'])
        
        # Calculate IntrinsicValue for both Calls and Puts
        valid_data = (
            pd.notna(df_merged['strike']) & 
            pd.notna(df_merged['live_stock_price']) &
            (is_call | is_put)  # Only for actual options
        )
        
        # For CALLS: IntrinsicValue = max(stock_price - strike, 0)
        # For PUTS:  IntrinsicValue = max(strike - stock_price, 0)
        df_merged['IntrinsicValue'] = np.where(
            valid_data & is_call,
            np.maximum(df_merged['live_stock_price'] - df_merged['strike'], 0.0),
            np.where(
                valid_data & is_put,
                np.maximum(df_merged['strike'] - df_merged['live_stock_price'], 0.0),
                np.nan
            )
        )
        
        # Calculate ExtrinsicValue = max(theoPrice - IntrinsicValue, 0) for ALL options
        valid_extrinsic = (
            (is_call | is_put) &
            pd.notna(df_merged['theoPrice']) & 
            pd.notna(df_merged['IntrinsicValue'])
        )
        
        df_merged['ExtrinsicValue'] = np.where(
            valid_extrinsic,
            np.maximum(df_merged['theoPrice'] - df_merged['IntrinsicValue'], 0.0),
            np.nan
        )
        
        # Print calculation statistics
        call_count = is_call.sum()
        put_count = is_put.sum()
        intrinsic_count = df_merged['IntrinsicValue'].notna().sum()
        extrinsic_count = df_merged['ExtrinsicValue'].notna().sum()
        
        print(f"   Call options found: {call_count:,}")
        print(f"   Put options found: {put_count:,}")
        print(f"   IntrinsicValue calculated: {intrinsic_count:,}")
        print(f"   ExtrinsicValue calculated: {extrinsic_count:,}")
        
        # Clean up temporary columns
        df_merged.drop(['option_type_from_symbol', 'unified_option_type'], axis=1, inplace=True, errors='ignore')
        
    except Exception as e:
        print(f"ERROR calculating option pricing columns: {e}")
        # Add empty columns if calculation fails
        df_merged['IntrinsicValue'] = np.nan
        df_merged['ExtrinsicValue'] = np.nan

    # Store merged DataFrame to file - only include columns that actually exist
    print(f"Storing merged DataFrame to: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
    
    # Filter to only include columns that exist in the dataframe
    available_columns = [col for col in DATAFRAME_DATA_MERGED_COLUMNS if col in df_merged.columns]
    missing_columns = [col for col in DATAFRAME_DATA_MERGED_COLUMNS if col not in df_merged.columns]
    
    if missing_columns:
        print(f"NOTE: {len(missing_columns)} configured columns not found in data: {missing_columns[:5]}..." if len(missing_columns) > 5 else f"NOTE: Missing columns: {missing_columns}")
    
    print(f"Saving {len(available_columns)} available columns out of {len(DATAFRAME_DATA_MERGED_COLUMNS)} configured")
    df_merged[available_columns].to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    
    # Print final statistics
    print(f"\n📊 Final DataFrame Statistics:")
    print(f"   Total rows: {len(df_merged):,}")
    print(f"   Total columns: {len(available_columns)}")
    print(f"   Unique symbols: {df_merged['symbol'].nunique()}")
    
    # Check if live prices were successfully merged
    if 'live_stock_price' in df_merged.columns:
        live_price_coverage = df_merged['live_stock_price'].notna().sum()
        coverage_pct = (live_price_coverage / len(df_merged)) * 100
        print(f"   Live price coverage: {live_price_coverage:,} rows ({coverage_pct:.1f}%)")



if __name__ == '__main__':
    import time

    start = time.time()
    merge_data_dataframes()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds") 