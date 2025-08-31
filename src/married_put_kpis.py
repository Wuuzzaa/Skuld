"""
Married Put KPIs - Standalone Module

Calculates precise married put strategy KPIs with real dividend modeling.
This module is called separately, NOT during the merge process.

Usage:
    python src/married_put_kpis.py

The module:
1. Loads the merged dataframe
2. Applies married put calculations ONLY to PUT options  
3. Saves results back to the merged dataframe
4. Shows detailed analysis for all calculated positions
"""

import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from src.married_put_dividend_kpis import calculate_precise_married_put_with_dividends


def calculate_all_married_put_kpis(df_combined, live_prices_dict=None, fee_per_trade=3.5):
    """
    Compatibility wrapper for Streamlit app.
    
    Calculate married put KPIs for a given dataframe (used by pages/iv_filter.py).
    This is a simplified version that works with the dataframe directly.
    
    Args:
        df_combined: Combined dataframe with stock and option data
        live_prices_dict: Dictionary with current stock prices (optional, unused)
        fee_per_trade: Trading fee per transaction (default: $3.5)
    
    Returns:
        DataFrame with married put KPI columns added
    """
    if df_combined.empty:
        return df_combined
    
    try:
        print(f"Calculating married put KPIs for {len(df_combined)} rows...")
        
        # Apply the precise married put calculations
        result_df = calculate_precise_married_put_with_dividends(df_combined, fee_per_trade=fee_per_trade)
        
        # Count successful calculations
        mp_calculated = result_df['MP_MaxRisk_Net'].notna().sum() if 'MP_MaxRisk_Net' in result_df.columns else 0
        print(f"✅ Calculated married put KPIs for {mp_calculated} PUT options")
        
        return result_df
        
    except Exception as e:
        print(f"Error in calculate_all_married_put_kpis: {e}")
        # Return original dataframe if calculation fails
        return df_combined


def apply_married_put_kpis_to_merged_data(fee_per_trade=3.5):
    """
    Load merged dataframe, apply married put KPIs, and save results.
    """
    print("=" * 80)
    print("MARRIED PUT KPIs - STANDALONE CALCULATION")
    print("=" * 80)
    
    try:
        # Load the merged dataframe
        print(f"📊 Loading merged dataframe from: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
        df_merged = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
        print(f"   Loaded {len(df_merged):,} rows with {len(df_merged.columns)} columns")
        
        # Show current data overview
        symbols = df_merged['symbol'].nunique()
        puts = df_merged['option-type'].str.lower().eq('put').sum() if 'option-type' in df_merged.columns else 0
        puts_alt = df_merged['option'].str.contains('P', na=False).sum() if 'option' in df_merged.columns else 0
        total_puts = max(puts, puts_alt)
        
        print(f"   Found {symbols} unique symbols")
        print(f"   Found {total_puts:,} PUT options for married put analysis")
        
        if total_puts == 0:
            print("❌ No PUT options found in merged data. Cannot calculate married put KPIs.")
            return None
        
        # Apply married put calculations
        print(f"\n🔄 Calculating Married Put KPIs with fee_per_trade=${fee_per_trade}...")
        df_with_mp = calculate_precise_married_put_with_dividends(df_merged, fee_per_trade=fee_per_trade)
        
        # Check results
        mp_calculated = df_with_mp['MP_MaxRisk_Net'].notna().sum()
        
        if mp_calculated == 0:
            print("❌ No married put KPIs were calculated. Check data and calculation logic.")
            return None
        
        print(f"✅ Successfully calculated married put KPIs for {mp_calculated:,} PUT options")
        
        # Save results back to merged dataframe
        print(f"\n💾 Saving updated dataframe with married put KPIs...")
        
        # Filter to only include configured columns that exist
        available_columns = [col for col in DATAFRAME_DATA_MERGED_COLUMNS if col in df_with_mp.columns]
        missing_columns = [col for col in DATAFRAME_DATA_MERGED_COLUMNS if col not in df_with_mp.columns]
        
        if missing_columns:
            print(f"   NOTE: {len(missing_columns)} configured columns not in data: {missing_columns[:3]}..." if len(missing_columns) > 3 else f"   NOTE: Missing columns: {missing_columns}")
        
        # Save the updated dataframe
        df_with_mp[available_columns].to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
        print(f"   Saved {len(available_columns)} columns to: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
        
        # Show detailed analysis of calculated married put positions
        show_married_put_analysis(df_with_mp)
        
        return df_with_mp
        
    except FileNotFoundError:
        print(f"❌ Merged dataframe not found at: {PATH_DATAFRAME_DATA_MERGED_FEATHER}")
        print("   Please run the data collection and merge process first.")
        return None
        
    except Exception as e:
        print(f"❌ Error applying married put KPIs: {e}")
        import traceback
        traceback.print_exc()
        return None


def show_married_put_analysis(df):
    """
    Show detailed analysis of calculated married put positions.
    """
    print("\n" + "=" * 80)
    print("MARRIED PUT ANALYSIS RESULTS")
    print("=" * 80)
    
    # Filter to only put options with calculated KPIs
    mp_data = df[df['MP_MaxRisk_Net'].notna()].copy()
    
    if len(mp_data) == 0:
        print("No married put data to analyze.")
        return
    
    # Group by symbol for summary
    try:
        symbol_summary = mp_data.groupby('symbol').agg({
            'MP_MaxRisk_Net': ['count', 'mean', 'min', 'max'],
            'MP_RiskPercent_Net': 'mean',
            'MP_EstimatedDividends': 'mean',
            'MP_DividendImpactPercent': 'mean',
            'strike': ['min', 'max'],
            'live_stock_price': 'first'
        }).round(2)
        
        symbol_summary.columns = ['Put_Count', 'Avg_Risk', 'Min_Risk', 'Max_Risk', 
                                 'Avg_Risk_Pct', 'Avg_Dividends', 'Avg_Div_Impact',
                                 'Min_Strike', 'Max_Strike', 'Stock_Price']
        
        print(f"\n📊 SUMMARY BY SYMBOL ({len(symbol_summary)} symbols with PUT options):")
        print("=" * 120)
        
        for symbol, row in symbol_summary.iterrows():
            print(f"\n{symbol} (Stock: ${row['Stock_Price']:.2f})")
            print(f"  Put Options Analyzed: {int(row['Put_Count'])}")
            print(f"  Strike Range: ${row['Min_Strike']:.0f} - ${row['Max_Strike']:.0f}")
            print(f"  Average Max Risk (Net): ${row['Avg_Risk']:.2f} ({row['Avg_Risk_Pct']:.1f}% of capital)")
            print(f"  Risk Range: ${row['Min_Risk']:.2f} - ${row['Max_Risk']:.2f}")
            print(f"  Average Dividends: ${row['Avg_Dividends']:.2f}")
            print(f"  Average Dividend Risk Reduction: {row['Avg_Div_Impact']:.1f}%")
    
    except Exception as e:
        print(f"Error in symbol summary: {e}")
        
    # Show top 10 best married put opportunities (lowest risk percentage)
    try:
        print(f"\n🎯 TOP 10 BEST MARRIED PUT OPPORTUNITIES (Lowest Risk %):")
        print("=" * 120)
        
        best_opportunities = mp_data.nsmallest(10, 'MP_RiskPercent_Net')[
            ['symbol', 'strike', 'live_stock_price', 'ask', 'MP_MaxRisk_Net', 
             'MP_RiskPercent_Net', 'MP_EstimatedDividends', 'MP_DividendImpactPercent',
             'MP_BreakevenUpside_Net']
        ].round(2)
        
        for i, (_, row) in enumerate(best_opportunities.iterrows(), 1):
            stock_price = row.get('live_stock_price', 'N/A')
            if pd.isna(stock_price):
                stock_price = 'N/A'
            else:
                stock_price = f"${stock_price:.2f}"
                
            print(f"\n{i:2d}. {row['symbol']} ${row['strike']:.0f} PUT")
            print(f"    Stock: {stock_price} | Put Premium: ${row['ask']:.2f}")
            print(f"    Max Risk: ${row['MP_MaxRisk_Net']:.2f} ({row['MP_RiskPercent_Net']:.1f}% of capital)")
            
            if pd.notna(row['MP_BreakevenUpside_Net']):
                print(f"    Breakeven: +{row['MP_BreakevenUpside_Net']:.1f}% stock move required")
            else:
                print(f"    Breakeven: N/A")
                
            print(f"    Dividends: ${row['MP_EstimatedDividends']:.2f} ({row['MP_DividendImpactPercent']:.1f}% risk reduction)")
            
    except Exception as e:
        print(f"Error in top opportunities analysis: {e}")
    
    # Show dividend impact statistics
    try:
        print(f"\n💰 DIVIDEND IMPACT ANALYSIS:")
        print("=" * 80)
        
        has_dividends = mp_data[mp_data['MP_EstimatedDividends'] > 0]
        no_dividends = mp_data[mp_data['MP_EstimatedDividends'] <= 0]
        
        print(f"Stocks with Dividends: {len(has_dividends):,} positions")
        if len(has_dividends) > 0:
            print(f"  Average Dividend Income: ${has_dividends['MP_EstimatedDividends'].mean():.2f}")
            print(f"  Average Risk Reduction: {has_dividends['MP_DividendImpactPercent'].mean():.1f}%")
            print(f"  Best Dividend Impact: {has_dividends['MP_DividendImpactPercent'].max():.1f}%")
        
        print(f"\nStocks without Dividends: {len(no_dividends):,} positions")
        if len(no_dividends) > 0:
            print(f"  Average Risk: {no_dividends['MP_RiskPercent_Net'].mean():.1f}% of capital")
        
        # Overall statistics
        print(f"\n📈 OVERALL MARRIED PUT STATISTICS:")
        print("=" * 80)
        print(f"Total PUT options analyzed: {len(mp_data):,}")
        print(f"Average Max Risk (Net): ${mp_data['MP_MaxRisk_Net'].mean():.2f}")
        print(f"Average Risk Percentage: {mp_data['MP_RiskPercent_Net'].mean():.1f}% of capital")
        print(f"Average Dividend Income: ${mp_data['MP_EstimatedDividends'].mean():.2f}")
        print(f"Average Dividend Risk Reduction: {mp_data['MP_DividendImpactPercent'].mean():.1f}%")
        print(f"Best Risk Percentage: {mp_data['MP_RiskPercent_Net'].min():.1f}%")
        print(f"Highest Dividend Impact: {mp_data['MP_DividendImpactPercent'].max():.1f}%")
        
    except Exception as e:
        print(f"Error in dividend impact analysis: {e}")


def get_married_put_kpis_for_symbol(symbol, strike_filter=None):
    """
    Get married put KPIs for a specific symbol.
    
    Args:
        symbol (str): Stock symbol (e.g., 'AAPL')
        strike_filter (float, optional): Show only specific strike price
    """
    try:
        df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
        
        # Filter for the symbol and put options with calculated KPIs
        symbol_data = df[
            (df['symbol'] == symbol) & 
            (df['MP_MaxRisk_Net'].notna())
        ].copy()
        
        if strike_filter:
            symbol_data = symbol_data[symbol_data['strike'] == strike_filter]
        
        if len(symbol_data) == 0:
            print(f"No married put KPIs found for {symbol}" + (f" strike ${strike_filter}" if strike_filter else ""))
            return None
        
        # Show detailed results
        print(f"\n🎯 MARRIED PUT KPIs for {symbol}" + (f" ${strike_filter} PUT" if strike_filter else ""))
        print("=" * 80)
        
        for _, row in symbol_data.iterrows():
            stock_price = row.get('live_stock_price', row.get('close', 'N/A'))
            if pd.isna(stock_price):
                stock_price = 'N/A'
            else:
                stock_price = f"${stock_price:.2f}"
                
            print(f"\nStrike: ${row['strike']:.0f} PUT")
            print(f"Stock Price: {stock_price}")
            print(f"Put Premium: ${row['ask']:.2f}")
            print(f"Intrinsic Value: ${row['MP_IntrinsicValue']:.2f}")
            print(f"Time Value: ${row['MP_TimeValue']:.2f}")
            print(f"Total Outlay: ${row['MP_TotalOutlay']:.2f}")
            print(f"Estimated Dividends: ${row['MP_EstimatedDividends']:.2f}")
            print(f"Max Risk (Net): ${row['MP_MaxRisk_Net']:.2f} ({row['MP_RiskPercent_Net']:.1f}% of capital)")
            print(f"Breakeven: ${row['MP_Breakeven_Net']:.2f} (+{row['MP_BreakevenUpside_Net']:.1f}%)")
            print(f"Dividend Risk Reduction: ${row['MP_DividendRiskReduction']:.2f} ({row['MP_DividendImpactPercent']:.1f}%)")
        
        return symbol_data
        
    except Exception as e:
        print(f"Error getting married put KPIs for {symbol}: {e}")
        return None


if __name__ == "__main__":
    # Run the married put KPI calculation
    result = apply_married_put_kpis_to_merged_data(fee_per_trade=3.5)
    
    if result is not None:
        print(f"\n✅ Married Put KPI calculation completed successfully!")
        print(f"   Updated merged dataframe saved with {len(result)} rows")
        
        # Example: Show specific symbol analysis
        print(f"\n" + "=" * 80)
        print("EXAMPLE: Detailed analysis for AAPL (if available)")
        print("=" * 80)
        get_married_put_kpis_for_symbol('AAPL')
    
    else:
        print(f"\n❌ Married Put KPI calculation failed!")
