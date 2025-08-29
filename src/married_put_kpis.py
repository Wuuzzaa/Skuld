"""
Married Put KPI Calculations - Working Version

This module provides comprehensive KPI calculations for married put strategies.
Compatible with the enhanced dataframe structure that includes universal 
IntrinsicValue and ExtrinsicValue calculations.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def calculate_all_married_put_kpis(df_combined, live_prices_dict=None, fee_per_trade=3.5):
    """
    Calculate all married put KPIs for the combined dataframe.
    
    Args:
        df_combined: Combined dataframe with stock and option data
        live_prices_dict: Dictionary with current stock prices (optional)
        fee_per_trade: Trading fee per transaction (default: $3.5)
    
    Returns:
        DataFrame with all KPI columns added
    """
    if df_combined.empty:
        return df_combined
    
    print(f"Starting KPI calculation for {len(df_combined)} rows...")
    
    # Make a copy to avoid modifying the original
    df = df_combined.copy()
    
    # Calculate basic protection metrics
    df = calculate_protection_level(df)
    df = calculate_cost_of_protection(df, fee_per_trade)
    df = calculate_cost_of_protection_percentage(df)
    
    # Calculate risk and reward metrics
    df = calculate_max_profit(df, fee_per_trade)
    df = calculate_max_profit_percentage(df)
    df = calculate_max_risk(df, fee_per_trade)
    df = calculate_max_risk_percentage(df)
    
    # Calculate time-based metrics
    df = calculate_days_to_expiration(df)
    df = calculate_annualized_protection_cost(df)
    df = calculate_breakeven_price(df, fee_per_trade)
    
    # Calculate advanced metrics
    df = calculate_upside_capture_ratio(df)
    df = calculate_time_decay_risk(df)
    df = calculate_implied_protection_yield(df)
    df = calculate_dividend_capture_potential(df)
    df = calculate_portfolio_hedge_efficiency(df)
    df = calculate_margin_impact(df)
    df = calculate_risk_reward_ratio(df)
    
    # Calculate enhanced metrics with fees and dividends
    df = calculate_cost_of_protection_with_fees(df, fee_per_trade)
    df = calculate_max_risk_with_fees_and_dividends(df, fee_per_trade)
    df = calculate_max_risk_percentage_with_fees_and_dividends(df, fee_per_trade)
    
    print(f"KPI calculation completed successfully for {len(df)} rows")
    return df


def calculate_protection_level(df):
    """Calculate the protection level (strike price as % of current stock price)"""
    df = df.copy()
    df['ProtectionLevel'] = (df['strike'] / df['close']) * 100
    return df


def calculate_cost_of_protection(df, fee_per_trade=3.5):
    """Calculate the absolute cost of protection (premium + fees)"""
    df = df.copy()
    df['CostOfProtection'] = df['ask'] + fee_per_trade
    return df


def calculate_cost_of_protection_percentage(df):
    """Calculate cost of protection as percentage of stock price"""
    df = df.copy()
    df['CostOfProtectionPercentage'] = (df['CostOfProtection'] / df['close']) * 100
    return df


def calculate_max_profit(df, fee_per_trade=1.0):
    """Calculate maximum profit potential (unlimited upside minus protection cost)"""
    df = df.copy()
    # For married puts, max profit is theoretically unlimited
    # We calculate profit at 10% stock appreciation as a reference
    stock_appreciation_10pct = df['close'] * 1.10
    df['MaxProfit'] = stock_appreciation_10pct - df['close'] - df['ask'] - (2 * fee_per_trade)
    return df


def calculate_max_profit_percentage(df):
    """Calculate maximum profit as percentage of initial investment"""
    df = df.copy()
    initial_investment = df['close'] + df['ask']
    df['MaxProfitPercentage'] = (df['MaxProfit'] / initial_investment) * 100
    return df


def calculate_max_risk(df, fee_per_trade=1.0):
    """Calculate maximum risk (stock falls to strike price)"""
    df = df.copy()
    df['MaxRisk'] = df['close'] - df['strike'] + df['ask'] + (2 * fee_per_trade)
    return df


def calculate_max_risk_percentage(df):
    """Calculate maximum risk as percentage of initial investment"""
    df = df.copy()
    initial_investment = df['close'] + df['ask']
    df['MaxRiskPercentage'] = (df['MaxRisk'] / initial_investment) * 100
    return df


def calculate_days_to_expiration(df):
    """Calculate days until option expiration"""
    df = df.copy()
    try:
        # Try different column names for expiration date
        expiration_col = None
        for col in ['expiration', 'expiration_date', 'exp_date', 'maturity']:
            if col in df.columns:
                expiration_col = col
                break
        
        if expiration_col is None:
            print("Warning: No expiration date column found")
            df['DaysToExpiration'] = 30  # Default fallback
            return df
        
        # Convert to datetime
        df['expiration'] = pd.to_datetime(df[expiration_col], errors='coerce')
        
        # Calculate days to expiration
        current_date = pd.Timestamp.now()
        df['DaysToExpiration'] = (df['expiration'] - current_date).dt.days
        
        # Convert to standard int to avoid numpy.int64 issues
        df['DaysToExpiration'] = df['DaysToExpiration'].astype('int32')
        
        # Set minimum to 0 for expired options
        df['DaysToExpiration'] = df['DaysToExpiration'].clip(lower=0)
        
    except Exception as e:
        print(f"Error calculating days to expiration: {e}")
        df['DaysToExpiration'] = 30  # Default fallback
    
    return df


def calculate_annualized_protection_cost(df):
    """Calculate annualized cost of protection"""
    df = df.copy()
    try:
        days_to_expiry = np.maximum(df['DaysToExpiration'], 1)  # Avoid division by zero
        df['AnnualizedProtectionCost'] = (df['CostOfProtectionPercentage'] * 365) / days_to_expiry
    except Exception as e:
        print(f"Error calculating annualized protection cost: {e}")
        df['AnnualizedProtectionCost'] = 0
    
    return df


def calculate_risk_reward_ratio(df):
    """Calculate risk-reward ratio"""
    df = df.copy()
    df['RiskRewardRatio'] = np.where(
        df['MaxProfit'] > 0,
        df['MaxRisk'] / df['MaxProfit'],
        np.inf
    )
    return df


def calculate_breakeven_price(df, fee_per_trade=1.0):
    """Calculate breakeven stock price"""
    df = df.copy()
    df['BreakevenPrice'] = df['close'] + df['ask'] + (2 * fee_per_trade)
    return df


def calculate_upside_capture_ratio(df):
    """Calculate upside capture ratio (how much upside is captured)"""
    df = df.copy()
    # For married puts, upside is captured 1:1 after breakeven
    df['UpsideCaptureRatio'] = 100.0  # 100% upside capture after breakeven
    return df


def calculate_time_decay_risk(df):
    """Calculate time decay risk (theta impact)"""
    df = df.copy()
    try:
        # Approximate theta as percentage of premium per day
        days_to_expiry = np.maximum(df['DaysToExpiration'], 1)
        df['TimeDecayRisk'] = (df['ask'] * 0.05) / days_to_expiry
    except Exception as e:
        print(f"Error calculating time decay risk: {e}")
        df['TimeDecayRisk'] = 0
    
    return df


def calculate_implied_protection_yield(df):
    """Calculate implied protection yield"""
    df = df.copy()
    try:
        df['ImpliedProtectionYield'] = df['AnnualizedProtectionCost']
    except Exception as e:
        print(f"Error calculating implied protection yield: {e}")
        df['ImpliedProtectionYield'] = 0
    
    return df


def calculate_dividend_capture_potential(df):
    """Calculate dividend capture potential during option period"""
    df = df.copy()
    try:
        # Use actual dividend yield if available, otherwise estimate
        if 'dividend_yield' in df.columns:
            dividend_yield = df['dividend_yield']
        else:
            dividend_yield = 2.0  # Default 2% annual yield
        
        years_to_expiry = df['DaysToExpiration'] / 365
        df['DividendCapturePotential'] = dividend_yield * years_to_expiry
    except Exception as e:
        print(f"Error calculating dividend capture potential: {e}")
        df['DividendCapturePotential'] = 0
    
    return df


def calculate_portfolio_hedge_efficiency(df):
    """Calculate hedge efficiency for portfolio protection"""
    df = df.copy()
    try:
        # Hedge efficiency as protection level relative to cost
        df['PortfolioHedgeEfficiency'] = df['ProtectionLevel'] / df['CostOfProtectionPercentage']
    except Exception as e:
        print(f"Error calculating portfolio hedge efficiency: {e}")
        df['PortfolioHedgeEfficiency'] = 0
    
    return df


def calculate_margin_impact(df):
    """Calculate margin impact of the married put strategy"""
    df = df.copy()
    try:
        # Married puts can reduce margin requirements
        df['MarginImpact'] = df['close'] * 0.25  # 25% margin relief
    except Exception as e:
        print(f"Error calculating margin impact: {e}")
        df['MarginImpact'] = 0
    
    return df


def calculate_cost_of_protection_with_fees(df, fee_per_trade=1.0):
    """Calculate cost of protection including all trading fees"""
    df = df.copy()
    # Total fees for complete strategy: buy stock + buy put + sell stock + exercise put
    total_fees = 4 * fee_per_trade
    
    df['CostOfProtectionWithFees'] = df['ask'] + total_fees
    df['CostOfProtectionWithFeesPercentage'] = (df['CostOfProtectionWithFees'] / df['close']) * 100
    return df


def calculate_max_risk_with_fees_and_dividends(df, fee_per_trade=1.0):
    """Calculate maximum risk including fees and potential dividend benefits"""
    df = df.copy()
    
    # Total trading fees
    total_fees = 4 * fee_per_trade
    
    # Basic max risk: stock decline to strike + premium + fees
    basic_max_risk = df['close'] - df['strike'] + df['ask'] + total_fees
    
    # Subtract potential dividend income
    if 'DividendCapturePotential' in df.columns:
        dividend_benefit = (df['DividendCapturePotential'] / 100) * df['close']
    else:
        # Estimate dividend benefit
        years_to_expiry = df.get('DaysToExpiration', 30) / 365
        dividend_benefit = (2.0 / 100) * df['close'] * years_to_expiry
    
    df['MaxRiskWithFeesAndDividends'] = np.maximum(basic_max_risk - dividend_benefit, 0)
    return df


def calculate_max_risk_percentage_with_fees_and_dividends(df, fee_per_trade=1.0):
    """Calculate maximum risk percentage including fees and dividends"""
    df = df.copy()
    
    if 'MaxRiskWithFeesAndDividends' not in df.columns:
        df = calculate_max_risk_with_fees_and_dividends(df, fee_per_trade)
    
    # Calculate as percentage of total investment
    initial_investment = df['close'] + df['ask'] + (2 * fee_per_trade)
    df['MaxRiskPercentageWithFeesAndDividends'] = (df['MaxRiskWithFeesAndDividends'] / initial_investment) * 100
    return df


def format_currency(value):
    """Format value as currency"""
    if pd.isna(value):
        return "N/A"
    return f"${value:.2f}"


def format_percentage(value):
    """Format value as percentage"""
    if pd.isna(value):
        return "N/A"
    return f"{value:.2f}%"


def get_kpi_summary(df_row):
    """Get a formatted summary of KPIs for a single row"""
    summary = {
        'Symbol': df_row.get('symbol', 'N/A'),
        'Strike': format_currency(df_row.get('strike', 0)),
        'Stock Price': format_currency(df_row.get('close', 0)),
        'Protection Level': format_percentage(df_row.get('ProtectionLevel', 0)),
        'Cost of Protection': format_currency(df_row.get('CostOfProtection', 0)),
        'Cost %': format_percentage(df_row.get('CostOfProtectionPercentage', 0)),
        'Max Risk': format_currency(df_row.get('MaxRisk', 0)),
        'Max Risk %': format_percentage(df_row.get('MaxRiskPercentage', 0)),
        'Days to Expiry': f"{df_row.get('DaysToExpiration', 0):.0f} days",
        'Annualized Cost': format_percentage(df_row.get('AnnualizedProtectionCost', 0)),
        'Hedge Efficiency': f"{df_row.get('PortfolioHedgeEfficiency', 0):.2f}",
        'Intrinsic Value': format_currency(df_row.get('IntrinsicValue', 0)),
        'Extrinsic Value': format_currency(df_row.get('ExtrinsicValue', 0))
    }
    return summary


if __name__ == "__main__":
    print("🔧 Married Put KPI Calculation Module")
    print("====================================")
    print("Main function: calculate_all_married_put_kpis(df)")
    print("This module calculates comprehensive KPIs for married put strategies.")
    
    # Test with sample data
    print("\n🧪 Testing with sample data...")
    sample_data = {
        'symbol': ['AAPL', 'MSFT'],
        'strike': [150.0, 300.0],
        'close': [160.0, 320.0],
        'ask': [5.50, 12.00],
        'expiration': ['2024-03-15', '2024-06-21'],
        'IntrinsicValue': [0.0, 0.0],  # OTM puts
        'ExtrinsicValue': [5.50, 12.00]
    }
    
    test_df = pd.DataFrame(sample_data)
    try:
        result = calculate_all_married_put_kpis(test_df)
        print("✅ Test successful!")
        print(f"Calculated {len([col for col in result.columns if col.endswith(('Level', 'Cost', 'Risk', 'Ratio', 'Efficiency'))])} KPI columns")
    except Exception as e:
        print(f"❌ Test failed: {e}")
