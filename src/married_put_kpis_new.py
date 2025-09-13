"""
Married Put KPIs - Modular Calculation Module

Calculates married put strategy KPIs with modular functions.
Uses database as data source for better performance.

Usage:
    python src/married_put_kpis.py

The module:
1. Loads relevant data from OptionDataMerged table
2. Calculates each KPI with separate functions
3. Combines all KPIs in main calculation function
"""

import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.database import select_into_dataframe


def load_option_data():
    """
    Load relevant option data from database for married put calculations.
    
    Returns:
        DataFrame with necessary columns for married put KPI calculations
    """
    print("Loading option data from database...")
    
    # Select relevant columns for married put calculations
    sql_query = """
        SELECT 
            symbol,
            strike,
            stock_price,
            theoPrice,
            bid,
            ask,
            mid,
            option_type
        FROM OptionDataMerged 
        WHERE option_type = 'PUT'
    """
    
    try:
        df = select_into_dataframe(sql_query)
        print(f"   Loaded {len(df):,} PUT options from database")
        print(f"   Found {df['symbol'].nunique()} unique symbols")
        return df
    except Exception as e:
        print(f"Error loading data from database: {e}")
        return pd.DataFrame()


def calculate_intrinsic_value(df):
    """
    Calculate intrinsic value for PUT options.
    
    Formula: max(strike - StockPrice, 0)
    
    Args:
        df: DataFrame with strike and stock price columns
        
    Returns:
        DataFrame with added 'MP_IntrinsicValue' column
    """
    df = df.copy()
    
    # Use stock_price as primary source, with fallbacks if needed
    stock_price = df['stock_price']
    
    # Calculate intrinsic value: max(strike - stock_price, 0) for PUT options
    df['MP_IntrinsicValue'] = np.maximum(df['strike'] - stock_price, 0)
    
    return df


def calculate_extrinsic_value(df):
    """
    Calculate extrinsic (time) value for PUT options.
    
    Formula: max(PutPrice - Intrinsic, 0)
    
    Args:
        df: DataFrame with option prices and intrinsic value
        
    Returns:
        DataFrame with added 'MP_ExtrinsicValue' column
    """
    df = df.copy()
    
    # Use theoPrice as primary, fallback to mid price from bid/ask
    put_price = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    
    # Calculate extrinsic value: max(put_price - intrinsic_value, 0)
    df['MP_ExtrinsicValue'] = np.maximum(put_price - df['MP_IntrinsicValue'], 0)
    
    return df


def calculate_all_married_put_kpis(df):
    """
    Calculate all married put KPIs by calling individual KPI functions.
    
    Args:
        df: DataFrame with option data
        
    Returns:
        DataFrame with all married put KPI columns added
    """
    print("\n" + "=" * 80)
    print("MARRIED PUT KPIs - MODULAR CALCULATION")
    print("=" * 80)
    
    if df.empty:
        print("No data provided for calculations")
        return df
    
    # Calculate each KPI step by step
    df = calculate_intrinsic_value(df)
    df = calculate_extrinsic_value(df)
    
    print(f"\nAll married put KPIs calculated successfully!")
    print(f"   Processed {len(df):,} PUT options")
    
    return df


if __name__ == "__main__":
    # Load data from database
    option_data = load_option_data()
    
    if not option_data.empty:
        # Calculate all KPIs
        result_data = calculate_all_married_put_kpis(option_data)
        
        # Show sample results
        if not result_data.empty:
            print(f"\nSAMPLE RESULTS:")
            print("=" * 80)
            sample_data = result_data[['symbol', 'strike', 'stock_price', 
                                     'MP_IntrinsicValue', 'MP_ExtrinsicValue']].head(5)
            print(sample_data.round(2))
    else:
        print("No data loaded - cannot calculate KPIs")