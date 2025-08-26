import pandas as pd

def analyze_fundamental_requirements():
    """
    Analyze which fundamental data we need for Married Put screener
    and check availability in existing data.
    """
    
    print("=== MARRIED PUT SCREENER - FUNDAMENTAL DATA ANALYSIS ===")
    
    # Load data
    fund_df = pd.read_csv('yahooquery_financial.csv', sep=';', decimal=',')
    main_df = pd.read_feather('data_merged.feather')
    
    print(f"Yahooquery Fundamentals: {fund_df.shape}")
    print(f"Main Dataframe: {main_df.shape}")
    print(f"Symbols in fundamentals: {list(fund_df['symbol'].unique())}")
    print(f"Symbols in main DF: {len(main_df['symbol'].unique())} unique")
    
    # Key fundamentals needed for advanced screener (based on screenshots)
    required_fundamentals = {
        # VALUATION METRICS
        'Stock Price': 'close',  # Already in main DF
        'Market Cap': 'MarketCap',
        'Price/Earnings': 'TotalRevenue',  # We'll need to calculate P/E from price/earnings
        'Price/Book': 'TangibleBookValue',  # Calculate P/B from market cap / book value
        'Enterprise Value': 'EnterpriseValue',
        
        # DIVIDEND METRICS
        'Dividend Yield': None,  # Need to calculate from DividendsPaid / MarketCap
        'Dividends Paid': 'CashDividendsPaid',
        
        # PROFITABILITY
        'Net Income': 'NetIncome',
        'Total Revenue': 'TotalRevenue', 
        'ROE': None,  # Calculate: NetIncome / StockholdersEquity
        'ROA': None,  # Calculate: NetIncome / TotalAssets
        
        # FINANCIAL HEALTH
        'Total Debt': 'TotalDebt',
        'Stockholders Equity': 'StockholdersEquity',
        'Total Assets': 'TotalAssets',
        'Current Assets': 'CurrentAssets',
        'Current Liabilities': 'CurrentLiabilities',
        
        # SHARES
        'Shares Outstanding': 'OrdinarySharesNumber',
        'Basic EPS': 'BasicEPS',
        'Diluted EPS': 'DilutedEPS',
        
        # CASHFLOW
        'Operating Cash Flow': 'OperatingCashFlow',
        'Free Cash Flow': 'FreeCashFlow',
        'EBITDA': 'EBITDA',
    }
    
    print("\n=== AVAILABILITY CHECK ===")
    
    fund_cols = fund_df.columns.tolist()
    main_cols = main_df.columns.tolist()
    
    available_direct = []
    need_calculation = []
    missing = []
    already_in_main = []
    
    for metric_name, column_name in required_fundamentals.items():
        if column_name is None:
            need_calculation.append(metric_name)
            print(f"CALCULATE: {metric_name}")
        elif column_name in fund_cols:
            if column_name in main_cols:
                already_in_main.append(metric_name)
                print(f"IN_MAIN: {metric_name} -> {column_name}")
            else:
                available_direct.append((metric_name, column_name))
                print(f"MERGE: {metric_name} -> {column_name}")
        else:
            missing.append(metric_name)
            print(f"MISSING: {metric_name} -> {column_name}")
    
    print(f"\n=== SUMMARY ===")
    print(f"Already in main DF: {len(already_in_main)}")
    print(f"Available for merge: {len(available_direct)}")
    print(f"Need calculation: {len(need_calculation)}")
    print(f"Missing completely: {len(missing)}")
    
    if available_direct:
        print(f"\nColumns to merge: {[col for _, col in available_direct]}")
    
    if need_calculation:
        print(f"\nNeed to calculate: {need_calculation}")
    
    if missing:
        print(f"\nMissing metrics: {missing}")
    
    # Check sample data
    print(f"\n=== SAMPLE DATA ===")
    latest_annual = fund_df[fund_df['periodType'] == 'annual'].groupby('symbol').last()
    
    key_metrics = ['MarketCap', 'NetIncome', 'TotalRevenue', 'TotalAssets', 'StockholdersEquity']
    available_metrics = [m for m in key_metrics if m in fund_cols]
    
    print("Sample data for key metrics:")
    for symbol in ['AAPL', 'A']:
        if symbol in latest_annual.index:
            print(f"\n{symbol}:")
            row = latest_annual.loc[symbol]
            for metric in available_metrics:
                value = row[metric]
                if pd.notna(value):
                    if 'Market' in metric or 'Revenue' in metric or 'Assets' in metric:
                        print(f"  {metric}: ${value/1e9:.1f}B")
                    else:
                        print(f"  {metric}: ${value/1e6:.1f}M")
                else:
                    print(f"  {metric}: N/A")

if __name__ == "__main__":
    analyze_fundamental_requirements()
