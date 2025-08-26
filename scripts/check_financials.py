import pandas as pd

def analyze_yahoo_financials():
    """Analyze Yahoo financial data for Must-Have metrics."""
    
    print("=== YAHOO FINANCIALS ANALYSIS ===")
    
    # Load data
    df = pd.read_csv('yahooquery_financial.csv', sep=';', decimal=',')
    
    print(f"Data shape: {df.shape}")
    print(f"Symbols: {list(df['symbol'].unique())}")
    print(f"Period types: {list(df['periodType'].unique())}")
    
    # Get all column names
    all_columns = df.columns.tolist()
    print(f"\nTotal columns: {len(all_columns)}")
    
    # Must-Have metrics for Married Put Screener
    must_have_searches = {
        'MARKET CAP': ['Market', 'Cap'],
        'DIVIDEND': ['Dividend', 'dividend'],
        'REVENUE': ['Revenue', 'TotalRevenue'],
        'NET INCOME': ['NetIncome', 'Income'],
        'TOTAL ASSETS': ['TotalAssets', 'Assets'],
        'DEBT': ['Debt', 'TotalDebt'],
        'EQUITY': ['Equity', 'StockholdersEquity'],
        'SHARES': ['Shares', 'Outstanding'],
        'EPS': ['EPS', 'BasicEPS', 'DilutedEPS'],
        'BOOK VALUE': ['Book', 'TangibleBook'],
        'CASH FLOW': ['CashFlow', 'Operating', 'Free'],
        'EBITDA': ['EBITDA'],
        'ENTERPRISE': ['Enterprise']
    }
    
    print("\n=== MUST-HAVE METRICS FOUND ===")
    
    found_metrics = {}
    
    for category, keywords in must_have_searches.items():
        matches = []
        for col in all_columns:
            if any(keyword in col for keyword in keywords):
                matches.append(col)
        
        found_metrics[category] = matches
        print(f"\n{category}:")
        if matches:
            for i, match in enumerate(matches):
                print(f"  {i+1}. {match}")
                if i >= 4:  # Limit to first 5
                    print(f"  ... and {len(matches)-5} more")
                    break
        else:
            print("  ❌ NOT FOUND")
    
    # Show sample data for key metrics
    print("\n=== SAMPLE DATA FOR KEY METRICS ===")
    
    # Get latest annual data per symbol
    annual_data = df[df['periodType'] == 'annual'].copy()
    latest_data = annual_data.groupby('symbol').last()
    
    key_columns = ['MarketCap', 'TotalRevenue', 'NetIncome', 'TotalAssets', 'StockholdersEquity', 'TotalDebt']
    available_key_cols = [col for col in key_columns if col in all_columns]
    
    print(f"Available key metrics: {available_key_cols}")
    
    for symbol in ['AAPL', 'A']:
        if symbol in latest_data.index:
            print(f"\n{symbol}:")
            row = latest_data.loc[symbol]
            for col in available_key_cols:
                value = row[col]
                if pd.notna(value) and value != 0:
                    if value > 1e9:
                        print(f"  {col}: ${value/1e9:.1f}B")
                    elif value > 1e6:
                        print(f"  {col}: ${value/1e6:.1f}M")
                    else:
                        print(f"  {col}: ${value:,.0f}")
                else:
                    print(f"  {col}: N/A")
    
    return found_metrics

if __name__ == "__main__":
    analyze_yahoo_financials()
