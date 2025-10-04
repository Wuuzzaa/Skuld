import pandas as pd
import numpy as np


def select_essential_fundamentals(df_fundamentals):
    """
    Select only the essential fundamental metrics needed for Married Put screening.
    Reduces from 238 columns to ~20 key metrics.
    
    Parameters:
    - df_fundamentals: Full fundamentals dataframe with all 238 columns
    
    Returns:
    - df_selected: Dataframe with only essential fundamentals + calculated ratios
    """
    
    # ESSENTIAL RAW FUNDAMENTALS (Must-Have from our analysis)
    essential_columns = {
        # VALUATION & SIZE
        'MarketCap': 'MarketCap',
        'EnterpriseValue': 'EnterpriseValue', 
        'TotalRevenue': 'TotalRevenue',
        'TotalAssets': 'TotalAssets',
        
        # PROFITABILITY
        'NetIncome': 'NetIncome',
        'EBITDA': 'EBITDA',
        'FreeCashFlow': 'FreeCashFlow',
        'OperatingCashFlow': 'OperatingCashFlow',
        
        # BALANCE SHEET
        'StockholdersEquity': 'StockholdersEquity',
        'TotalDebt': 'TotalDebt',
        'CurrentAssets': 'CurrentAssets', 
        'CurrentLiabilities': 'CurrentLiabilities',
        'TangibleBookValue': 'TangibleBookValue',
        
        # SHARES & DIVIDENDS
        'OrdinarySharesNumber': 'OrdinarySharesNumber',
        'BasicEPS': 'BasicEPS',
        'DilutedEPS': 'DilutedEPS',
        'CashDividendsPaid': 'CashDividendsPaid',
        
        # META COLUMNS
        'symbol': 'symbol',
        'asOfDate': 'asOfDate',
        'periodType': 'periodType'
    }
    
    # Check which columns actually exist in the dataframe
    available_columns = {}
    missing_columns = []
    
    for display_name, column_name in essential_columns.items():
        if column_name in df_fundamentals.columns:
            available_columns[display_name] = column_name
        else:
            missing_columns.append(display_name)
    
    print(f"Found {len(available_columns)}/{len(essential_columns)} essential columns")
    if missing_columns:
        print(f"Missing columns: {missing_columns}")
    
    # Select only available columns
    selected_df = df_fundamentals[[col for col in available_columns.values()]].copy()
    
    # Rename columns to display names for clarity
    column_mapping = {v: k for k, v in available_columns.items()}
    selected_df = selected_df.rename(columns=column_mapping)
    
    return selected_df


def calculate_fundamental_ratios(df_selected):
    """
    Calculate essential financial ratios from selected fundamental data.
    
    Parameters:
    - df_selected: Dataframe with essential fundamentals
    
    Returns:
    - df_with_ratios: Dataframe with additional calculated ratio columns
    """
    
    df_ratios = df_selected.copy()
    
    # VALUATION RATIOS
    # P/E Ratio = Market Cap / Net Income
    df_ratios['PE_Ratio'] = np.where(
        (df_ratios['NetIncome'] > 0) & (df_ratios['MarketCap'] > 0),
        df_ratios['MarketCap'] / df_ratios['NetIncome'],
        np.nan
    )
    
    # P/B Ratio = Market Cap / Tangible Book Value  
    df_ratios['PB_Ratio'] = np.where(
        (df_ratios['TangibleBookValue'] > 0) & (df_ratios['MarketCap'] > 0),
        df_ratios['MarketCap'] / df_ratios['TangibleBookValue'],
        np.nan
    )
    
    # P/S Ratio = Market Cap / Total Revenue
    df_ratios['PS_Ratio'] = np.where(
        (df_ratios['TotalRevenue'] > 0) & (df_ratios['MarketCap'] > 0),
        df_ratios['MarketCap'] / df_ratios['TotalRevenue'],
        np.nan
    )
    
    # FINANCIAL HEALTH RATIOS
    # Debt/Equity Ratio = Total Debt / Stockholders Equity
    df_ratios['DebtEquity_Ratio'] = np.where(
        (df_ratios['StockholdersEquity'] > 0) & (df_ratios['TotalDebt'] >= 0),
        df_ratios['TotalDebt'] / df_ratios['StockholdersEquity'],
        np.nan
    )
    
    # Current Ratio = Current Assets / Current Liabilities
    df_ratios['CurrentRatio'] = np.where(
        (df_ratios['CurrentLiabilities'] > 0) & (df_ratios['CurrentAssets'] > 0),
        df_ratios['CurrentAssets'] / df_ratios['CurrentLiabilities'],
        np.nan
    )
    
    # PROFITABILITY RATIOS  
    # ROE = Net Income / Stockholders Equity
    df_ratios['ROE'] = np.where(
        (df_ratios['StockholdersEquity'] > 0) & (df_ratios['NetIncome'].notna()),
        df_ratios['NetIncome'] / df_ratios['StockholdersEquity'],
        np.nan
    )
    
    # ROA = Net Income / Total Assets
    df_ratios['ROA'] = np.where(
        (df_ratios['TotalAssets'] > 0) & (df_ratios['NetIncome'].notna()),
        df_ratios['NetIncome'] / df_ratios['TotalAssets'],
        np.nan
    )
    
    # DIVIDEND METRICS
    # Dividend Yield = Cash Dividends Paid / Market Cap (annualized)
    df_ratios['DividendYield_Calc'] = np.where(
        (df_ratios['MarketCap'] > 0) & (df_ratios['CashDividendsPaid'] < 0),  # Dividends are negative in cashflow
        abs(df_ratios['CashDividendsPaid']) / df_ratios['MarketCap'],
        np.nan
    )
    
    # EFFICIENCY RATIOS
    # Profit Margin = Net Income / Total Revenue
    df_ratios['ProfitMargin'] = np.where(
        (df_ratios['TotalRevenue'] > 0) & (df_ratios['NetIncome'].notna()),
        df_ratios['NetIncome'] / df_ratios['TotalRevenue'],
        np.nan
    )
    
    # EBITDA Margin = EBITDA / Total Revenue
    df_ratios['EBITDAMargin'] = np.where(
        (df_ratios['TotalRevenue'] > 0) & (df_ratios['EBITDA'].notna()),
        df_ratios['EBITDA'] / df_ratios['TotalRevenue'],
        np.nan
    )
    
    print(f"Calculated {10} additional financial ratios")
    
    return df_ratios


def prepare_fundamentals_for_merge(df_full_fundamentals):
    """
    Complete pipeline: Select essential fundamentals + calculate ratios.
    
    Parameters:
    - df_full_fundamentals: Raw fundamentals with all 238 columns
    
    Returns:
    - df_ready: Clean dataframe ready for merging (~30 columns)
    """
    
    print("=== PREPARING FUNDAMENTALS FOR MERGE ===")
    print(f"Input: {df_full_fundamentals.shape}")
    
    # Step 1: Select only essential fundamentals
    df_selected = select_essential_fundamentals(df_full_fundamentals)
    print(f"After selection: {df_selected.shape}")
    
    # Step 2: Calculate financial ratios
    df_with_ratios = calculate_fundamental_ratios(df_selected)
    print(f"After ratio calculation: {df_with_ratios.shape}")
    
    # Step 3: Get latest annual data per symbol (for merging)
    annual_data = df_with_ratios[df_with_ratios['periodType'] == 'annual'].copy()
    
    if annual_data.empty:
        print("WARNING: No annual data found, using all available data")
        latest_data = df_with_ratios.groupby('symbol').last().reset_index()
    else:
        latest_data = annual_data.groupby('symbol').last().reset_index()
    
    print(f"Final for merge: {latest_data.shape}")
    print(f"Symbols: {list(latest_data['symbol'].unique())}")
    
    # Drop meta columns that aren't needed in final merge
    merge_columns = [col for col in latest_data.columns 
                    if col not in ['asOfDate', 'periodType']]
    
    df_ready = latest_data[merge_columns].copy()
    
    print(f"Ready for merge: {df_ready.shape}")
    print(f"Columns: {list(df_ready.columns)}")
    
    return df_ready


if __name__ == "__main__":
    # Test the function
    import pandas as pd
    
    df_full = pd.read_csv('yahooquery_financial.csv', sep=';', decimal=',')
    print(f"Testing with full data: {df_full.shape}")
    
    df_prepared = prepare_fundamentals_for_merge(df_full)
    
    print("\n=== SAMPLE OUTPUT ===")
    print(df_prepared.head())
