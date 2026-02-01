import pandas as pd
import numpy as np
import logging
import sys
import os
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add parent directory to path for imports if needed
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def calculate_cagr(start_val, end_val, years):
    """Calculates Compound Annual Growth Rate."""
    if start_val <= 0 or years <= 0:
        return 0.0
    return ((end_val / start_val) ** (1 / years)) - 1

def determine_classification(years_growth):
    """Determines dividend classification based on years of growth."""
    if years_growth >= 25:
        return "Champion"
    elif years_growth >= 10:
        return "Contender"
    elif years_growth >= 5:
        return "Challenger"
    else:
        return "n/a"

def calculate_metrics_for_symbol(symbol, df_dividends, current_price, current_yield_percent):
    """
    Calculates dividend metrics for a single symbol using its historical dividend dataframe.
    
    Args:
        symbol (str): Ticker symbol.
        df_dividends (pd.DataFrame): DataFrame with 'Date' and 'Dividend' columns.
        current_price (float): Current asset price.
        current_yield_percent (float): Current dividend yield (e.g., 3.5 for 3.5%).
        
    Returns:
        dict: Calculated metrics.
    """
    metrics = {
        'Symbol': symbol,
        'DGR-1Y': None,
        'DGR-3Y': None,
        'DGR-5Y': None,
        'DGR-10Y': None,
        'No-Years': 0,
        'Chowder-Number': None,
        'Classification': 'n/a',
        'Payouts/-Year': 0,
        'Annualized': 0.0
    }
    
    if df_dividends is None or df_dividends.empty:
        return metrics

    # Ensure date is datetime
    df_dividends['Date'] = pd.to_datetime(df_dividends['Date'])
    df_dividends = df_dividends.sort_values('Date')
    
    # 1. Payout Frequency (Last 12 months)
    one_year_ago = datetime.now() - pd.DateOffset(years=1)
    recent_divs = df_dividends[df_dividends['Date'] > one_year_ago]
    metrics['Payouts/-Year'] = len(recent_divs)
    
    if metrics['Payouts/-Year'] > 0:
         metrics['Annualized'] = recent_divs['Dividend'].sum()
    
    # 2. Annualize Dividends by Year
    df_dividends['Year'] = df_dividends['Date'].dt.year
    annual_divs = df_dividends.groupby('Year')['Dividend'].sum()
    
    # --- IMPROVED LOGIC: Use TTM (Trailing 12 Months) for 'Current' value ---
    # This avoids problems with incomplete calendar years.
    
    # Calculate TTM Sum
    one_year_ago = df_dividends['Date'].max() - pd.DateOffset(years=1)
    ttm_divs = df_dividends[df_dividends['Date'] > one_year_ago]
    val_now_ttm = ttm_divs['Dividend'].sum()
    
    # For history, use Calendar Years
    # Calculate DGR comparing TTM vs (Year - N)
    # Caution: Comparing TTM (rolling) with Calendar Year (static) is acceptable approximation,
    # or we can calculate TTM-N-Years-Ago. Simpler is Calendar Years, but let's stick to standard Reference Years.
    
    # Let's try: Reference Year = Last Full Complete Year (e.g. 2025 if now is 2026)
    target_year = datetime.now().year - 1
    
    # If using Calendar Years for history:
    val_now = annual_divs.get(target_year, 0)
    
    # If the target year (2025) seems incomplete (e.g. sum < TTM * 0.8), maybe we should use TTM?
    # Let's rely on TTM for the "Current Rate" used in CAGR end-point if checking 'current' growth.
    # Standard Chowder: "5Y CAGR" is usually (Div_Current / Div_5y_ago)^(1/5).
    # Div_Current = Annualized Current Dividend (Rate).
    
    # Let's use the 'Annualized' value derived from recent payouts as 'End Value'
    # If not enough recent payouts, fallback to TTM sum.
    current_rate = metrics['Annualized']
    if current_rate == 0:
        current_rate = val_now_ttm
        
    for period in [1, 3, 5, 10]:
        # Start Year = Current Year - Period
        # Use Calendar Year Sum for Start Value
        # e.g. 2026 - 5 = 2021.
        start_year = datetime.now().year - period
        
        # Adjust: If we use TTM as 'Now', we are effectively at 'Now'.
        # So look back P years from Now.
        
        # Simpler approach: Compare Year(Now-1) vs Year(Now-1-P)
        # e.g. 2025 vs 2020. This is stable.
        
        start_year_stable = target_year - period
        val_start = annual_divs.get(start_year_stable, 0)
        val_end_stable = annual_divs.get(target_year, 0)
        
        if val_start > 0 and val_end_stable > 0:
            cagr = calculate_cagr(val_start, val_end_stable, period)
            metrics[f'DGR-{period}Y'] = round(cagr * 100, 2)
            
    # Chowder Number
    dgr_5y = metrics['DGR-5Y']
    if dgr_5y is not None and current_yield_percent is not None:
        metrics['Chowder-Number'] = round(current_yield_percent + dgr_5y, 2)
        
    # Years of Growth
    # Strictly check: Year N > Year N-1
    streak = 0
    check_year = target_year
    
    # Basic check: Is 2025 > 2024?
    # Optimization: Allow flat? No, strictly growth.
    
    while True:
        curr = annual_divs.get(check_year, 0)
        prev = annual_divs.get(check_year - 1, 0)
        
        if prev > 0 and curr > prev:
            streak += 1
            check_year -= 1
        else:
            break
            
    metrics['No-Years'] = streak
    metrics['Classification'] = determine_classification(streak)
    metrics['Streak-Basis'] = 'D' # Default to Dividend based streak
    
    # --- Placeholders for Advanced Metrics (Requiring Price History/Other Data) ---
    # These would need 'price_history' dataframe or similar inputs.
    
    # TTR (Total Total Return) = (Price_End - Price_Start + Divs_Received) / Price_Start
    # if price_history is available:
    #    metrics['TTR-1Y'] = calculate_ttr(...)
    #    metrics['TTR-3Y'] = calculate_ttr(...)
    
    # Fair Value (FV)
    # Could be derived from Analyst Targets or P/E Mean.
    # metrics['Fair-Value'] = ...
    # metrics['FV-%'] = ... (Price / FV) - 1
    
    return metrics


    return metrics


def main_calculation_job():
    """
    [TODO: DB DEVELOPER]
    Main Execution Function & SQL MAPPING (BATCH OPTIMIZED).
    
    -------------------------------------------------------
    SQL SCHEMA MAPPING INSTRUCTIONS
    -------------------------------------------------------
    The DB Developer must map the keys from 'metrics' dictionary 
    to the "FundamentalDataDividendRadar" table columns:
    
    ... (Same Schema as above) ...
    
    ALGORITHM (BATCH PROCESSING):
    -------------------------------------------------------
    1. **BATCH FETCH**: Fetch ALL rows from 'Dividends' table into a single Pandas DataFrame (`df_all_divs`).
       - Query: `SELECT * FROM Dividends` (or filter by relevant symbols).
       - This avoids N+1 queries (Querying DB 1000 times for 1000 symbols).
       
    2. **BATCH FETCH FUNDAMENTALS**: Fetch current Price/Yield for all symbols into `df_fundamentals`.
    
    3. **GROUP & PROCESS**:
       - Iterate `df_all_divs.groupby('Symbol')`.
       - For each group, look up price/yield in `df_fundamentals` (O(1) lookup).
       - Call `calculate_metrics_for_symbol`.
       
    4. **BULK UPSERT**: Collect all results and perform a single (or chunked) DB insertion.
    -------------------------------------------------------
    """
    logger.info("Starting Dividend Metrics Calculation Job (Batch Mode)...")
    
    # [TODO: DB DEVELOPER]
    # 1. Fetch ALL Dividend Data (Batch)
    # df_div_data_all = pd.read_sql("SELECT * FROM Dividends", db_connection)
    df_div_data_all = pd.DataFrame(columns=['Symbol', 'Date', 'Dividend']) # Placeholder
    
    # [TODO: DB DEVELOPER]
    # 2. Fetch Latest Fundamentals (Price, Yield)
    # df_fundamentals = pd.read_sql("SELECT Symbol, Price, YieldPct FROM StockPrice ...", db_connection)
    df_fundamentals = pd.DataFrame(columns=['Symbol', 'Price', 'YieldPct']).set_index('Symbol') # Placeholder
    
    logger.info(f"Loaded {len(df_div_data_all)} dividend rows and {len(df_fundamentals)} fundamental records.")
    
    results = []
    
    # EFFICIENT PROCESSING: GroupBy
    # Get unique symbols from dividends (or from master symbol list)
    # EFFICIENT PROCESSING: GroupBy
    # Get unique symbols from dividends (or from master symbol list)
    grouped = df_div_data_all.groupby('Symbol')
    
    total_symbols = len(grouped)
    processed_count = 0
    
    for symbol, df_div in grouped:
        try:
            # Lookup fundamental data (with fallback)
            if symbol in df_fundamentals.index:
                price = df_fundamentals.loc[symbol, 'Price']
                yield_pct = df_fundamentals.loc[symbol, 'YieldPct']
            else:
                price = 0.0
                yield_pct = 0.0
            
            # Calculation
            metrics = calculate_metrics_for_symbol(
                symbol, 
                df_div, 
                price, 
                yield_pct
            )
            results.append(metrics)
            
        except Exception as e:
            logger.error(f"Error calculating metrics for {symbol}: {e}")
            
        processed_count += 1
        if processed_count % 100 == 0:
            logger.info(f"Processed {processed_count}/{total_symbols} symbols...")
            
    df_results = pd.DataFrame(results)
    
    print("\n--- Calculated Metrics Output (Batch Mode) ---")
    print(df_results.T)
    print("\n----------------------------------------------")
    
    # [TODO: DB DEVELOPER]
    # Implement BULK SAVE here.
    
    logger.info("Calculation Job Finished.")

if __name__ == "__main__":
    main_calculation_job()
