import pandas as pd
import numpy as np
from math import sqrt
from scipy.stats import norm
from datetime import datetime, timedelta
from config import *


def calculate_married_put_kpis(row, dividend_data=None, risk_free_rate=0.05):
    """
    Calculate comprehensive KPIs for married put positions.
    
    Parameters:
    - row: DataFrame row with option and stock data
    - dividend_data: Dictionary with dividend information per symbol
    - risk_free_rate: Risk-free rate for PV calculations
    
    Returns:
    - dict: Complete KPI calculations
    """
    spot = row['close']
    strike = row['strike']
    option_price = row['ask']  # Cost to buy the put
    option_bid = row['bid']
    delta = row['delta']
    iv = row['iv'] / 100  # Convert to decimal
    expiration_date = pd.to_datetime(str(row['expiration_date']), format='%Y%m%d')
    today = pd.Timestamp(datetime.today().date())
    
    # Basic Time Calculations
    dte = (expiration_date - today).days
    t_years = dte / 365.0
    
    # Intrinsic and Extrinsic Value
    intrinsic_value = max(strike - spot, 0)  # For puts
    extrinsic_value = max(option_price - intrinsic_value, 0)
    
    # Cost Metrics
    extrinsic_pct_spot = extrinsic_value / spot
    annual_cost = extrinsic_value / t_years if t_years > 0 else 0
    monthly_cost = annual_cost / 12
    
    # Breakeven Calculations
    breakeven_uplift = option_price / spot
    
    # Dividend Adjustments
    dividend_yield = 0
    dividend_pv = 0
    dividend_frequency = 0
    
    if dividend_data and row['symbol'] in dividend_data:
        div_info = dividend_data[row['symbol']]
        dividend_yield = div_info.get('yield', 0)
        dividend_pv = div_info.get('pv_to_expiry', 0)
        dividend_frequency = div_info.get('frequency', 0)
    
    # Dividend-adjusted breakeven
    if dividend_yield > 0:
        breakeven_uplift_div_adj = (option_price - dividend_yield * spot * t_years) / spot
        net_cashflow_ratio = dividend_yield - (annual_cost / spot)
    else:
        breakeven_uplift_div_adj = breakeven_uplift
        net_cashflow_ratio = -(annual_cost / spot)
    
    # Investment and Loss Calculations
    total_investment = (spot * 100) + (option_price * 100)  # 100 shares + 1 put contract
    max_loss_abs = total_investment - (strike * 100)
    max_loss_pct = max_loss_abs / total_investment
    
    # Protection Metrics
    protection_level_floor_pct = strike / spot
    cost_of_protection_pct = option_price / spot
    
    # Delta and Exposure
    net_delta = abs(1 + delta)  # Stock delta (1) + Put delta (negative)
    
    # Upside Participation (20% rally scenario)
    upside_participation_20pct = max(1 - (option_price / (0.2 * spot)), 0)
    upside_participation_20pct = min(upside_participation_20pct, 1)
    
    # Liquidity Metrics
    bid_ask_spread_pct = (option_price - option_bid) / ((option_price + option_bid) / 2) if (option_price + option_bid) > 0 else 0
    
    # Skew (placeholder - would need ATM IV for comparison)
    skew_premium = 0  # Will calculate if ATM data available
    
    # Return on Investment Proxy
    # Higher protection level with lower cost = better ROI
    roi_score = (protection_level_floor_pct / cost_of_protection_pct) if cost_of_protection_pct > 0 else 0
    
    # Risk-Adjusted Return Score
    # Accounts for time, dividends, and protection level
    risk_adj_return = (
        (protection_level_floor_pct * 100) +  # Protection value
        (net_cashflow_ratio * 100 * t_years) -  # Dividend benefit
        (cost_of_protection_pct * 100)  # Cost penalty
    )
    
    return {
        # Time Metrics
        'dte': dte,
        't_years': t_years,
        
        # Value Components
        'intrinsic_value': intrinsic_value,
        'extrinsic_value': extrinsic_value,
        'extrinsic_pct_spot': extrinsic_pct_spot * 100,  # As percentage
        
        # Cost Metrics
        'annual_cost': annual_cost,
        'monthly_cost': monthly_cost,
        'cost_of_protection_pct': cost_of_protection_pct * 100,
        
        # Breakeven Metrics
        'breakeven_uplift': breakeven_uplift * 100,  # As percentage
        'breakeven_uplift_div_adj': breakeven_uplift_div_adj * 100,
        'net_cashflow_ratio': net_cashflow_ratio * 100,
        
        # Investment & Loss
        'total_investment': total_investment,
        'max_loss_abs': max_loss_abs,
        'max_loss_pct': max_loss_pct * 100,
        
        # Protection
        'protection_level_floor_pct': protection_level_floor_pct * 100,
        
        # Exposure
        'net_delta': net_delta,
        'upside_participation_20pct': upside_participation_20pct * 100,
        
        # Liquidity
        'bid_ask_spread_pct': bid_ask_spread_pct * 100,
        
        # Dividend Info
        'dividend_yield': dividend_yield * 100,
        'dividend_pv': dividend_pv,
        'dividend_frequency': dividend_frequency,
        
        # Return Scores
        'roi_score': roi_score,
        'risk_adj_return': risk_adj_return
    }


def prepare_dividend_data(fundamentals_df, symbols_list):
    """
    Extract dividend information from fundamentals dataframe.
    
    Parameters:
    - fundamentals_df: Fundamentals dataframe
    - symbols_list: List of symbols to process
    
    Returns:
    - dict: Dividend data per symbol
    """
    if fundamentals_df is None or fundamentals_df.empty:
        return {}
    
    dividend_data = {}
    
    # Look for dividend-related columns
    dividend_yield_cols = [col for col in fundamentals_df.columns 
                          if 'dividend' in col.lower() and 'yield' in col.lower()]
    
    for symbol in symbols_list:
        symbol_data = fundamentals_df[fundamentals_df['symbol'] == symbol]
        if not symbol_data.empty:
            # Get latest annual data
            annual_data = symbol_data[symbol_data['periodType'] == 'annual']
            if not annual_data.empty:
                latest = annual_data.iloc[-1]
                
                yield_value = 0
                if dividend_yield_cols:
                    yield_col = dividend_yield_cols[0]
                    if yield_col in latest and pd.notna(latest[yield_col]):
                        yield_value = float(latest[yield_col])
                
                dividend_data[symbol] = {
                    'yield': yield_value / 100,  # Convert to decimal
                    'pv_to_expiry': 0,  # Placeholder for now
                    'frequency': 4  # Assume quarterly by default
                }
    
    return dividend_data


def find_atm_iv(df, symbol, spot_price, expiration_date):
    """
    Find ATM implied volatility for skew calculation.
    
    Parameters:
    - df: Options dataframe
    - symbol: Stock symbol
    - spot_price: Current stock price
    - expiration_date: Option expiration date
    
    Returns:
    - float: ATM implied volatility
    """
    # Filter for same symbol, expiration, and option type (puts for consistency)
    options = df[
        (df['symbol'] == symbol) & 
        (df['expiration_date'] == expiration_date) &
        (df['option-type'] == 'put')
    ].copy()
    
    if options.empty:
        return None
    
    # Find strike closest to spot
    options['strike_diff'] = abs(options['strike'] - spot_price)
    atm_option = options.loc[options['strike_diff'].idxmin()]
    
    return atm_option['iv'] if pd.notna(atm_option['iv']) else None


def __load_df_option_columns_only(df, expiration_date):
    """
    Filter dataframe for specific expiration date and required columns.
    """
    option_columns = [
        "symbol",
        "expiration_date", 
        "option-type",
        "strike",
        "ask",
        "bid",
        "delta",
        "gamma",
        "iv",
        "rho",
        "theoPrice", 
        "theta",
        "vega",
        "option",
        "close",
        "earnings_date"
    ]
    
    # Filter expiration date and only needed columns
    df_filtered = df[df["expiration_date"] == expiration_date]
    df_filtered = df_filtered[option_columns].copy()
    
    return df_filtered


def get_puts_by_criteria(df, delta_min=0.15, delta_max=0.45, min_volume=10):
    """
    Select put options based on screening criteria.
    
    Parameters:
    - df: Options dataframe
    - delta_min (float): Minimum delta (absolute value)
    - delta_max (float): Maximum delta (absolute value) 
    - min_volume (int): Minimum daily volume (placeholder for future)
    
    Returns:
    - puts_df: Filtered puts dataframe
    """
    # Filter for puts only
    puts = df[df["option-type"] == "put"].copy()
    
    # Convert delta to absolute values for easier comparison
    puts["abs_delta"] = puts["delta"].abs()
    
    # Apply delta filters
    puts_filtered = puts[
        (puts["abs_delta"] >= delta_min) & 
        (puts["abs_delta"] <= delta_max)
    ].copy()
    
    # Remove rows with missing critical data
    puts_filtered = puts_filtered.dropna(subset=["ask", "bid", "delta", "iv", "close"])
    
    # Filter out options with zero bid/ask
    puts_filtered = puts_filtered[
        (puts_filtered["ask"] > 0) & 
        (puts_filtered["bid"] > 0)
    ]
    
    return puts_filtered


def apply_fundamental_filters(df, fundamentals_df, filters):
    """
    Apply fundamental screening filters to the dataframe.
    
    Parameters:
    - df: Options dataframe
    - fundamentals_df: Fundamentals dataframe from yahooquery (processed)
    - filters: Dictionary with filter criteria
    
    Returns:
    - filtered_df: Dataframe after applying fundamental filters
    """
    if fundamentals_df is None or fundamentals_df.empty:
        return df
    
    # The processed fundamentals already contain latest data per symbol
    # Merge with options data
    df_merged = df.merge(fundamentals_df, on="symbol", how="left")
    
    # Apply filters if provided
    if filters:
        for filter_name, filter_value in filters.items():
            if filter_name in df_merged.columns and filter_value is not None:
                if isinstance(filter_value, dict):
                    # Range filter (min/max)
                    if "min" in filter_value and filter_value["min"] is not None:
                        df_merged = df_merged[df_merged[filter_name] >= filter_value["min"]]
                    if "max" in filter_value and filter_value["max"] is not None:
                        df_merged = df_merged[df_merged[filter_name] <= filter_value["max"]]
                else:
                    # Exact value filter
                    df_merged = df_merged[df_merged[filter_name] == filter_value]
    
    return df_merged


def get_married_puts(df, expiration_date, filters=None):
    """
    Main function to filter dataframe and calculate married put KPIs on-the-fly.
    
    Parameters:
    - df: Complete merged dataframe with all data (options, technicals, fundamentals)
    - expiration_date: Expiration date (integer YYYYMMDD format)
    - filters: Dictionary with all filter criteria (technicals, fundamentals, options)
    
    Returns:
    - filtered_df_with_kpis: Filtered dataframe with married put KPIs added
    """
    # Step 1: Filter by expiration date and option type
    df_filtered = df[
        (df["expiration_date"] == expiration_date) & 
        (df["option-type"] == "put")
    ].copy()
    
    if df_filtered.empty:
        return pd.DataFrame()
    
    # Step 2: Apply all filters if provided
    if filters:
        df_filtered = apply_comprehensive_filters(df_filtered, filters)
    
    if df_filtered.empty:
        return pd.DataFrame()
    
    # Step 3: Calculate married put KPIs on-the-fly for filtered data only
    kpi_results = []
    
    for idx, row in df_filtered.iterrows():
        # Calculate comprehensive KPIs for this specific option
        kpis = calculate_married_put_kpis(row)
        
        # Add KPIs as new columns to the row
        row_with_kpis = row.to_dict()
        row_with_kpis.update(kpis)
        kpi_results.append(row_with_kpis)
    
    # Step 4: Create final dataframe with all original data + KPIs
    result_df = pd.DataFrame(kpi_results)
    
    # Step 5: Sort by ROI Score (best opportunities first)
    if 'roi_score' in result_df.columns:
        result_df = result_df.sort_values('roi_score', ascending=False).reset_index(drop=True)
    
    return result_df


def apply_comprehensive_filters(df, filters):
    """
    Apply all filter criteria to the dataframe.
    
    Parameters:
    - df: Dataframe to filter
    - filters: Dictionary with filter criteria categorized by type
    
    Example filters structure:
    {
        "options": {
            "delta_min": 0.15,
            "delta_max": 0.45,
            "iv_min": 0.20,
            "bid_min": 0.10
        },
        "technicals": {
            "RSI_min": 30,
            "RSI_max": 70,
            "MACD_min": -0.5
        },
        "fundamentals": {
            "PE_Ratio_max": 25,
            "MarketCap_min": 1000000000,
            "ROE_Fund_min": 0.10
        },
        "liquidity": {
            "max_spread_pct": 10.0,
            "min_volume": 100
        }
    }
    """
    df_filtered = df.copy()
    
    # Apply Options Filters
    if "options" in filters:
        options_filters = filters["options"]
        
        # Delta filters
        if "delta_min" in options_filters and options_filters["delta_min"] is not None:
            df_filtered = df_filtered[df_filtered["delta"].abs() >= options_filters["delta_min"]]
        if "delta_max" in options_filters and options_filters["delta_max"] is not None:
            df_filtered = df_filtered[df_filtered["delta"].abs() <= options_filters["delta_max"]]
        
        # IV filters
        if "iv_min" in options_filters and options_filters["iv_min"] is not None:
            df_filtered = df_filtered[df_filtered["iv"] >= options_filters["iv_min"]]
        if "iv_max" in options_filters and options_filters["iv_max"] is not None:
            df_filtered = df_filtered[df_filtered["iv"] <= options_filters["iv_max"]]
        
        # Bid/Ask filters
        if "bid_min" in options_filters and options_filters["bid_min"] is not None:
            df_filtered = df_filtered[df_filtered["bid"] >= options_filters["bid_min"]]
        if "ask_max" in options_filters and options_filters["ask_max"] is not None:
            df_filtered = df_filtered[df_filtered["ask"] <= options_filters["ask_max"]]
        
        # Strike filters
        if "strike_min" in options_filters and options_filters["strike_min"] is not None:
            df_filtered = df_filtered[df_filtered["strike"] >= options_filters["strike_min"]]
        if "strike_max" in options_filters and options_filters["strike_max"] is not None:
            df_filtered = df_filtered[df_filtered["strike"] <= options_filters["strike_max"]]
    
    # Apply Technical Filters
    if "technicals" in filters:
        tech_filters = filters["technicals"]
        
        for indicator, value in tech_filters.items():
            if value is not None and indicator in df_filtered.columns:
                if indicator.endswith("_min"):
                    col_name = indicator.replace("_min", "")
                    if col_name in df_filtered.columns:
                        df_filtered = df_filtered[df_filtered[col_name] >= value]
                elif indicator.endswith("_max"):
                    col_name = indicator.replace("_max", "")
                    if col_name in df_filtered.columns:
                        df_filtered = df_filtered[df_filtered[col_name] <= value]
    
    # Apply Fundamental Filters
    if "fundamentals" in filters:
        fund_filters = filters["fundamentals"]
        
        for metric, value in fund_filters.items():
            if value is not None and metric in df_filtered.columns:
                if metric.endswith("_min"):
                    col_name = metric.replace("_min", "")
                    if col_name in df_filtered.columns:
                        df_filtered = df_filtered[df_filtered[col_name] >= value]
                elif metric.endswith("_max"):
                    col_name = metric.replace("_max", "")
                    if col_name in df_filtered.columns:
                        df_filtered = df_filtered[df_filtered[col_name] <= value]
    
    # Apply Liquidity Filters
    if "liquidity" in filters:
        liq_filters = filters["liquidity"]
        
        # Calculate bid-ask spread on-the-fly
        if "max_spread_pct" in liq_filters and liq_filters["max_spread_pct"] is not None:
            df_filtered = df_filtered[
                (df_filtered["ask"] > 0) & (df_filtered["bid"] > 0)
            ].copy()
            
            mid_price = (df_filtered["ask"] + df_filtered["bid"]) / 2
            spread_pct = ((df_filtered["ask"] - df_filtered["bid"]) / mid_price) * 100
            df_filtered = df_filtered[spread_pct <= liq_filters["max_spread_pct"]]
        
        # Volume filter (if available)
        if "min_volume" in liq_filters and liq_filters["min_volume"] is not None:
            if "volume" in df_filtered.columns:
                df_filtered = df_filtered[df_filtered["volume"] >= liq_filters["min_volume"]]
    
    return df_filtered


if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """
    import time
    
    # Test with sample data
    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    expiration_date = '2025-05-30'
    
    # Sample filters
    filters = {
        "delta_min": 0.20,
        "delta_max": 0.40,
        "min_volume": 5,
        "max_spread_pct": 15.0,
        "min_oi": 5
    }
    
    start = time.time()
    married_puts_df = get_married_puts(df, expiration_date, filters=filters)
    end = time.time()
    
    print(f"Found {len(married_puts_df)} married put opportunities")
    
    if not married_puts_df.empty:
        # Show key KPIs
        print("\n=== TOP 5 BY ROI SCORE ===")
        top_5 = married_puts_df.head(5)
        key_cols = ['symbol', 'strike', 'cost_of_protection_pct', 'protection_level_floor_pct', 
                   'max_loss_pct', 'roi_score', 'risk_adj_return']
        print(top_5[key_cols].to_string())
        
        print(f"\n=== SUMMARY STATISTICS ===")
        print(f"Average Cost of Protection: {married_puts_df['cost_of_protection_pct'].mean():.2f}%")
        print(f"Average Max Loss: {married_puts_df['max_loss_pct'].mean():.2f}%")
        print(f"Average Protection Level: {married_puts_df['protection_level_floor_pct'].mean():.2f}%")
        print(f"Best ROI Score: {married_puts_df['roi_score'].max():.2f}")
    
    print(f"Runtime: {end - start:.6f} seconds")
