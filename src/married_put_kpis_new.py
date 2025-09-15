"""
Married Put KPIs - Modular Calc    # Select relevant columns for married put calculations
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
from datetime import datetime
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
    # Using OptionDataMerged view to get the data we see in database browser
    sql_query = """
        SELECT 
            symbol,
            strike,
            "option-type" AS option_type, 
            expiration_date,
            "theoPrice" AS theoPrice,
            bid,
            ask,
            close,
            "Payouts/-Year" AS payouts_per_year,
            "Summary_dividendYield"
        FROM OptionDataMerged
        WHERE "option-type" = 'put' 
    """

 #Remove later    
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
    
    # Use close as primary source (fallback until live_stock_price is available)
    stock_price = df['close']
    
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


def calculate_extrinsic_percentage(df):
    """
    Calculate extrinsic value as percentage of stock price.
    
    Formula: Extrinsic / StockPrice * 100
    
    Args:
        df: DataFrame with extrinsic value and stock price
        
    Returns:
        DataFrame with added 'MP_ExtrinsicPercentage' column
    """
    df = df.copy()
    
    # Calculate extrinsic percentage: (Extrinsic / close) * 100
    df['MP_ExtrinsicPercentage'] = np.where(
        (df['close'] > 0) & (df['MP_ExtrinsicValue'] >= 0),
        (df['MP_ExtrinsicValue'] / df['close']) * 100,
        np.nan
    )
    
    return df


def calculate_annual_cost(df):
    """
    Calculate annualized cost of the extrinsic value.
    
    Formula: Extrinsic / T_years
    Where T_years is calculated from expiration_date
    
    Args:
        df: DataFrame with extrinsic value and expiration_date
        
    Returns:
        DataFrame with added 'MP_AnnualCost' column
    """
    df = df.copy()
    
    # Convert expiration_date to datetime and calculate days to expiration (DTE)
    
    current_date = datetime.now()
    
    # Assuming expiration_date is in format YYYYMMDD (integer)
    df['expiration_datetime'] = pd.to_datetime(df['expiration_date'], format='%Y%m%d', errors='coerce')
    df['DTE'] = (df['expiration_datetime'] - current_date).dt.days
    
    # Calculate T_years (time to expiration in years)
    df['T_years'] = df['DTE'] / 365.25
    
    # Calculate annual cost: Extrinsic / T_years
    df['MP_AnnualCost'] = np.where(
        (df['T_years'] > 0) & (df['MP_ExtrinsicValue'] >= 0),
        df['MP_ExtrinsicValue'] / df['T_years'],
        np.nan
    )
    
    # Clean up temporary columns
    df.drop(['expiration_datetime'], axis=1, inplace=True, errors='ignore')
    
    return df


def calculate_monthly_cost(df):
    """
    Calculate monthly cost of the married put strategy.
    
    Formula: AnnualCost / 12
    
    Args:
        df: DataFrame with annual cost calculated
        
    Returns:
        DataFrame with added 'MP_MonthlyCost' column
    """
    df = df.copy()
    
    # Calculate monthly cost: AnnualCost / 12
    df['MP_MonthlyCost'] = np.where(
        df['MP_AnnualCost'] >= 0,
        df['MP_AnnualCost'] / 12,
        np.nan
    )
    
    return df


def calculate_breakeven_uplift(df):
    """
    Calculate breakeven uplift percentage for the married put strategy.
    
    Formula: theoPrice / StockPrice * 100
    Shows how much the stock needs to drop for the put to break even.
    
    Args:
        df: DataFrame with theoPrice and stock prices
        
    Returns:
        DataFrame with added 'MP_BreakevenUplift' column
    """
    df = df.copy()
    
    # Use theoPrice as put price (theoretical option price)
    put_price = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    
    # Calculate breakeven uplift: (theoPrice / StockPrice) * 100
    df['MP_BreakevenUplift'] = np.where(
        (df['close'] > 0) & (put_price >= 0),
        (put_price / df['close']) * 100,
        np.nan
    )
    
    return df


def calculate_dividend_sum_to_expiry(df, shares):
    """
    Calculate expected dividend sum from now until option expiration.
    
    Formula: Based on dividend yield, stock price, time to expiry, and number of shares
    
    Args:
        df: DataFrame with dividend data and expiration dates
        shares: Number of shares (must be provided)
        
    Returns:
        DataFrame with added 'MP_DividendSumToExpiry' column
    """
    df = df.copy()
    
    # Convert expiration_date to datetime and calculate days to expiration (DTE)
    current_date = datetime.now()
    df['expiration_datetime'] = pd.to_datetime(df['expiration_date'], format='%Y%m%d', errors='coerce')
    df['DTE'] = (df['expiration_datetime'] - current_date).dt.days
    
    # Calculate years to expiry
    df['years_to_expiry'] = df['DTE'] / 365.25
    
    # Get dividend yield and payment frequency
    dividend_yield_percent = df['Summary_dividendYield'].fillna(0)
    
    # Check for missing payouts_per_year data and warn
    missing_payouts = df['payouts_per_year'].isna().sum()
    if missing_payouts > 0:
        print(f"WARNING: Missing payouts_per_year data for {missing_payouts} records - using default value of 4 (quarterly)")
    
    payouts_per_year = df['payouts_per_year'].fillna(4)  # Default to quarterly if missing
    
    # Calculate annual dividend per share from dividend yield
    # Formula: dividend_yield_decimal * stock_price = annual_dividend_per_share
    # Note: Summary_dividendYield is already in decimal format (e.g., 0.0463 for 4.63%)
    annual_dividend_per_share = dividend_yield_percent * df['close']
    
    # Calculate expected dividend sum to expiry for the specified number of shares
    # Formula: annual_dividend_per_share * shares * years_to_expiry
    df['MP_DividendSumToExpiry'] = np.where(
        (df['years_to_expiry'] > 0) & (dividend_yield_percent >= 0) & (df['close'] > 0),
        annual_dividend_per_share * shares * df['years_to_expiry'],
        0
    )
    
    # Clean up temporary columns
    df.drop(['expiration_datetime', 'years_to_expiry'], axis=1, inplace=True, errors='ignore')
    
    return df


def calculate_dividend_adjusted_breakeven(df):
    """
    Calculate dividend-adjusted breakeven for married put strategy.
    
    Formula: (theoPrice - DividendSumToExpiry) / StockPrice * 100
    Shows how much stock needs to drop considering dividend income.
    
    Args:
        df: DataFrame with theoPrice, dividend sum, and stock price
        
    Returns:
        DataFrame with added 'MP_DividendAdjustedBreakeven' column
    """
    df = df.copy()
    
    # Use theoPrice as put price
    put_price = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    
    # Calculate dividend-adjusted breakeven: (PutPrice - DividendSum) / StockPrice * 100
    net_put_cost = put_price - df['MP_DividendSumToExpiry']
    
    df['MP_DividendAdjustedBreakeven'] = np.where(
        (df['close'] > 0) & (put_price >= 0),
        (net_put_cost / df['close']) * 100,
        np.nan
    )
    
    return df


def calculate_net_cashflow_ratio(df, shares):
    """
    Calculate net cashflow ratio for married put strategy.
    
    Formula: (Dividend_Annual_for_shares / StockPrice_for_shares) - (AnnualCost / StockPrice_for_shares)
    Shows net annual cashflow as percentage of stock investment for specified number of shares.
    
    Args:
        df: DataFrame with dividend, annual cost, and stock price data
        shares: Number of shares (must be provided)
        
    Returns:
        DataFrame with added 'MP_NetCashflowRatio' column
    """
    df = df.copy()
    
    # Calculate annual dividend per share from dividend yield
    dividend_yield_percent = df['Summary_dividendYield'].fillna(0)
    # Note: Summary_dividendYield is already in decimal format (e.g., 0.0463 for 4.63%)
    annual_dividend_per_share = dividend_yield_percent * df['close']
    
    # Calculate total annual dividend for the specified number of shares
    total_annual_dividend = annual_dividend_per_share * shares
    
    # Calculate total stock investment for the specified number of shares
    total_stock_investment = df['close'] * shares
    
    # Calculate dividend yield ratio (total dividend / total stock investment)
    dividend_ratio = np.where(
        total_stock_investment > 0,
        total_annual_dividend / total_stock_investment,
        0
    )
    
    # Calculate annual cost ratio (annual cost / total stock investment)
    # Note: AnnualCost is already per option contract (covers 100 shares worth of protection)
    annual_cost_ratio = np.where(
        total_stock_investment > 0,
        df['MP_AnnualCost'] / total_stock_investment,
        0
    )
    
    # Net cashflow ratio = dividend ratio - cost ratio
    df['MP_NetCashflowRatio'] = (dividend_ratio - annual_cost_ratio) * 100  # Convert to percentage
    
    return df


def calculate_total_investment(df, shares):
    """
    Calculate total investment required for married put strategy.
    
    Formula: (StockPrice * shares) + (PutPrice * contracts_needed)
    Shows total capital required for the strategy.
    Note: One put contract covers 100 shares, so we need shares/100 contracts.
    
    Args:
        df: DataFrame with stock price and put price data
        shares: Number of shares to buy (must be provided)
        
    Returns:
        DataFrame with added 'MP_TotalInvestment' column
    """
    df = df.copy()
    
    # Calculate number of put contracts needed (each contract covers 100 shares)
    contracts_needed = shares / 100
    
    # Use theoPrice as put price per contract
    put_price_per_contract = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    
    # Calculate stock investment (price per share * number of shares)
    stock_investment = df['close'] * shares
    
    # Calculate total put premium (price per contract * number of contracts * 100)
    total_put_premium = put_price_per_contract * contracts_needed * 100
    
    # Total investment = stock cost + put premium
    df['MP_TotalInvestment'] = stock_investment + total_put_premium
    
    return df


def calculate_max_loss_abs(df, shares):
    """
    Calculate maximum absolute loss for married put strategy.
    
    Formula: TotalInvestment - (strike * shares)
    Shows the maximum absolute loss if the stock drops to or below the strike price.
    The put option protects against losses below the strike, so max loss is the difference
    between total investment and what the puts secure (strike * shares).
    
    Args:
        df: DataFrame with total investment and strike data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_MaxLossAbs' column
    """
    df = df.copy()
    
    # Calculate what the puts secure (strike price * number of shares)
    put_protection_value = df['strike'] * shares
    
    # Max loss = Total investment minus what puts protect
    df['MP_MaxLossAbs'] = df['MP_TotalInvestment'] - put_protection_value
    
    return df


def calculate_max_loss_percentage(df, shares):
    """
    Calculate maximum loss percentage for married put strategy.
    
    Formula: (MaxLossAbs / TotalInvestment) * 100
    Shows the maximum loss as percentage of total investment.
    This indicates what percentage of the total capital is at risk in the worst-case scenario.
    Result is already in percentage format (e.g., 81.5 for 81.5%).
    
    Args:
        df: DataFrame with MaxLossAbs and TotalInvestment data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_MaxLossPercentage' column (in percentage format)
    """
    df = df.copy()
    
    # Calculate max loss percentage: (MaxLossAbs / TotalInvestment) * 100
    # Avoid division by zero and multiply by 100 for percentage format
    df['MP_MaxLossPercentage'] = np.where(
        df['MP_TotalInvestment'] != 0,
        (df['MP_MaxLossAbs'] / df['MP_TotalInvestment']) * 100,
        0
    )
    
    return df


def calculate_floor_percentage(df, shares):
    """
    Calculate floor percentage for married put strategy.
    
    Formula: (strike / StockPrice) * 100
    Shows at what percentage of the current stock price the put protection kicks in.
    Higher values mean better protection (put strikes closer to current price).
    
    Args:
        df: DataFrame with strike and stock price data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_FloorPercentage' column (in percentage format)
    """
    df = df.copy()
    
    # Use close as stock price (primary source until live_stock_price is available)
    stock_price = df['close']
    
    # Calculate floor percentage: (strike / StockPrice) * 100
    # Avoid division by zero
    df['MP_FloorPercentage'] = np.where(
        stock_price > 0,
        (df['strike'] / stock_price) * 100,
        0
    )
    
    return df


def calculate_capital_at_risk_per_time(df, shares):
    """
    Calculate Capital-at-Risk per Time for married put strategy.
    
    Formula: Max Loss Abs / T_years
    Shows how much capital is at risk per year (annualized risk).
    Useful to compare strategies with different time horizons.
    
    Args:
        df: DataFrame with MaxLossAbs and T_years data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_CapitalAtRiskPerTime' column
    """
    df = df.copy()
    
    # Calculate Capital-at-Risk per Time: MaxLossAbs / T_years
    # Avoid division by zero
    df['MP_CapitalAtRiskPerTime'] = np.where(
        df['T_years'] > 0,
        df['MP_MaxLossAbs'] / df['T_years'],
        0
    )
    
    return df


def calculate_capital_efficiency_score(df, shares):
    """
    Calculate Capital Efficiency Score for married put strategy.
    
    Formula: Floor % / Annual Cost %
    Shows how much "safety level" you get per percent of insurance costs.
    Higher values = more efficient capital usage.
    
    Args:
        df: DataFrame with FloorPercentage and AnnualCost data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_CapitalEfficiencyScore' column
    """
    df = df.copy()
    
    # First calculate Annual Cost as percentage of stock investment
    total_stock_investment = df['close'] * shares
    annual_cost_percentage = np.where(
        total_stock_investment > 0,
        (df['MP_AnnualCost'] / total_stock_investment) * 100,
        0
    )
    
    # Calculate Capital Efficiency Score: Floor % / Annual Cost %
    # Avoid division by zero
    df['MP_CapitalEfficiencyScore'] = np.where(
        annual_cost_percentage > 0,
        df['MP_FloorPercentage'] / annual_cost_percentage,
        0
    )
    
    return df


def calculate_break_even_time(df, shares):
    """
    Calculate Break-Even Time for married put strategy.
    
    Formula: Total Put Cost for Shares / Total Annual Dividends for Shares
    Shows how long you must hold the stock (including dividends) until insurance costs are covered.
    Result in years. If > option expiry, dividends don't cover insurance costs.
    
    Args:
        df: DataFrame with theoPrice, dividend yield, and stock price data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_BreakEvenTime' column (in years)
    """
    df = df.copy()
    
    # Use theoPrice as put price per contract
    put_price_per_contract = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    

    # Calculate total put cost for all shares
    total_put_cost = put_price_per_contract * shares
    
    # Calculate annual dividend per share from dividend yield
    dividend_yield_decimal = df['Summary_dividendYield'].fillna(0)
    annual_dividend_per_share = dividend_yield_decimal * df['close']
    
    # Calculate total annual dividends for all shares
    total_annual_dividends = annual_dividend_per_share * shares
    
    # Calculate Break-Even Time: Total Put Cost / Total Annual Dividends
    df['MP_BreakEvenTime'] = np.where(
        total_annual_dividends > 0,
        total_put_cost / total_annual_dividends,
        np.inf  # If no dividends, break-even time is infinite
    )
    
    # Replace infinite values with a large number for display purposes
    df['MP_BreakEvenTime'] = df['MP_BreakEvenTime'].replace([np.inf, -np.inf], 999999)
    
    return df


def calculate_dividend_coverage_ratio(df, shares):
    """
    Calculate Dividend Coverage Ratio for married put strategy.
    
    Formula: (Total Dividends for all shares over option period) / (Total Put Cost for all shares)
    Shows how much of the put premium is covered by dividends over the option period.
    Values > 1.0 mean dividends fully cover the insurance costs.
    
    Args:
        df: DataFrame with dividend, put price, and time data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_DividendCoverageRatio' column
    """
    df = df.copy()
    
    # Use theoPrice as put price per contract
    put_price_per_contract = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    
    # Calculate number of contracts needed for the given shares
    contracts_needed = shares / 100
    
    # Calculate total put cost for all shares
    total_put_cost = put_price_per_contract * contracts_needed
    
    # Calculate annual dividend per share from dividend yield
    dividend_yield_decimal = df['Summary_dividendYield'].fillna(0)
    annual_dividend_per_share = dividend_yield_decimal * df['close']
    
    # Calculate total dividends for all shares over the option period
    total_dividends_all_shares = annual_dividend_per_share * shares * df['T_years']
    
    # Calculate Dividend Coverage Ratio: Total Dividends / Total Put Cost
    df['MP_DividendCoverageRatio'] = np.where(
        total_put_cost > 0,
        total_dividends_all_shares / total_put_cost,
        0
    )
    
    return df


def calculate_time_value_ratio(df, shares):
    """
    Calculate Time Value Ratio (Zeitwertquote) for married put strategy.
    
    Formula: Extrinsic / Put Price * 100
    Shows how much of the option price is "decaying time value".
    Lower values = more efficient (you buy more intrinsic value, less time decay).
    
    Args:
        df: DataFrame with extrinsic value and put price data
        shares: Number of shares in the strategy (must be provided)
        
    Returns:
        DataFrame with added 'MP_TimeValueRatio' column (in percentage format)
    """
    df = df.copy()
    
    # Use theoPrice as put price per contract
    put_price_per_contract = df['theoPrice'].fillna((df['bid'] + df['ask']) / 2)
    
    # Calculate Time Value Ratio: (Extrinsic / Put Price) * 100
    # Avoid division by zero
    df['MP_TimeValueRatio'] = np.where(
        put_price_per_contract > 0,
        (df['MP_ExtrinsicValue'] / put_price_per_contract) * 100,
        0
    )
    
    return df


def calculate_all_married_put_kpis(df, shares):
    """
    Calculate all married put KPIs by calling individual KPI functions.
    
    Args:
        df: DataFrame with option data
        shares: Number of shares for the strategy (must be provided)
        
    Returns:
        DataFrame with all married put KPI columns added
    """
    print("\n" + "=" * 80)
    print("MARRIED PUT KPIs - MODULAR CALCULATION")
    print("=" * 80)
    print(f"Calculating for {shares} shares per strategy")
    
    if df.empty:
        print("No data provided for calculations")
        return df
    
    # Calculate each KPI step by step
    df = calculate_intrinsic_value(df)
    df = calculate_extrinsic_value(df)
    df = calculate_extrinsic_percentage(df)
    df = calculate_time_value_ratio(df, shares)              # NEW KPI
    df = calculate_annual_cost(df)
    df = calculate_monthly_cost(df)
    df = calculate_breakeven_uplift(df)
    df = calculate_dividend_sum_to_expiry(df, shares)
    df = calculate_dividend_adjusted_breakeven(df)
    df = calculate_net_cashflow_ratio(df, shares)
    df = calculate_total_investment(df, shares)
    df = calculate_max_loss_abs(df, shares)
    df = calculate_max_loss_percentage(df, shares)
    df = calculate_floor_percentage(df, shares)
    df = calculate_capital_at_risk_per_time(df, shares)
    df = calculate_capital_efficiency_score(df, shares)
    df = calculate_break_even_time(df, shares)
    df = calculate_dividend_coverage_ratio(df, shares)
    
    print(f"\nAll married put KPIs calculated successfully!")
    print(f"   Processed {len(df):,} PUT options")
    print(f"   Calculated 18 KPIs: Intrinsic, Extrinsic, Extrinsic%, Time Value Ratio, Annual Cost, Monthly Cost, Breakeven Uplift, Dividend Sum, Dividend-Adj Breakeven, Net Cashflow Ratio, Total Investment, Max Loss Abs, Max Loss %, Floor %, Capital at Risk/Time, Capital Efficiency Score, Break-Even Time, Dividend Coverage Ratio")
    
    return df


if __name__ == "__main__":
    # CENTRAL CONFIGURATION: Define number of shares for all calculations
    SHARES = 200  # Number of shares to buy (determines all strategy calculations)
    
    # Load data from database
    option_data = load_option_data()
    
    if not option_data.empty:
        # Calculate all KPIs using the centrally defined shares value
        result_data = calculate_all_married_put_kpis(option_data, shares=SHARES)
        
        # Show sample results
        if not result_data.empty:
            print(f"\nCOMPLETE RESULTS - STRUCTURED VIEW:")
            print("=" * 150)
            
            # Set pandas display options
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', None)
            pd.set_option('display.max_colwidth', 12)
            pd.set_option('display.max_rows', None)  # Show ALL rows, not just first 5
            
            # Group 1: Basic Option Info
            print("\n1. BASIC OPTION INFO:")
            print("-" * 80)
            basic_cols = ['symbol', 'strike', 'option_type', 'expiration_date', 'close', 'theoPrice', 'bid', 'ask']
            print(result_data[basic_cols].round(4))
            
            # Group 2: Dividend Data
            print("\n2. DIVIDEND DATA:")
            print("-" * 80)
            dividend_cols = ['symbol', 'payouts_per_year', 'Summary_dividendYield']
            print(result_data[dividend_cols].round(4))
            
            # Group 3: Basic KPIs
            print("\n3. BASIC KPIs:")
            print("-" * 80)
            basic_kpi_cols = ['symbol', 'MP_IntrinsicValue', 'MP_ExtrinsicValue', 'MP_ExtrinsicPercentage', 'MP_BreakevenUplift', 'MP_FloorPercentage']
            print(result_data[basic_kpi_cols].round(4))
            
            # Group 4: COST ANALYSIS:
            print("\n4. COST ANALYSIS:")
            print("-" * 80)
            cost_cols = ['symbol', 'MP_AnnualCost', 'MP_MonthlyCost', 'MP_TotalInvestment', 'MP_MaxLossAbs', 'MP_MaxLossPercentage']
            print(result_data[cost_cols].round(4))
            
            # Group 5: Dividend-Adjusted Analysis
            print("\n5. DIVIDEND-ADJUSTED ANALYSIS:")
            print("-" * 80)
            dividend_analysis_cols = ['symbol', 'MP_DividendSumToExpiry', 'MP_DividendAdjustedBreakeven', 'MP_NetCashflowRatio']
            print(result_data[dividend_analysis_cols].round(4))
            
            # Group 6: Advanced KPIs
            print("\n6. ADVANCED KPIs:")
            print("-" * 80)
            advanced_kpi_cols = ['symbol', 'MP_CapitalAtRiskPerTime', 'MP_CapitalEfficiencyScore', 'MP_BreakEvenTime', 'MP_DividendCoverageRatio']
            print(result_data[advanced_kpi_cols].round(4))
    else:
        print("No data loaded - cannot calculate KPIs")