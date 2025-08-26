import pandas as pd
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *


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

    # Store merged DataFrame to file - only include columns that actually exist
    print(f"Storing merged DataFrame to: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
    
    # Filter to only include columns that exist in the dataframe
    available_columns = [col for col in DATAFRAME_DATA_MERGED_COLUMNS if col in df_merged.columns]
    missing_columns = [col for col in DATAFRAME_DATA_MERGED_COLUMNS if col not in df_merged.columns]
    
    if missing_columns:
        print(f"NOTE: {len(missing_columns)} configured columns not found in data: {missing_columns[:5]}..." if len(missing_columns) > 5 else f"NOTE: Missing columns: {missing_columns}")
    
    print(f"Saving {len(available_columns)} available columns out of {len(DATAFRAME_DATA_MERGED_COLUMNS)} configured")
    df_merged[available_columns].to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)



if __name__ == '__main__':
    import time

    start = time.time()
    merge_data_dataframes()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds") 