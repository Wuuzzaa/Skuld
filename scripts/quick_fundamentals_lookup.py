"""
Quick fundamental data lookup tool
Simple script to get key metrics for any symbol
"""

import pandas as pd
from yahooquery import Ticker


def quick_lookup(symbol):
    """
    Get key fundamental metrics for a single symbol
    """
    print(f"Quick Fundamental Lookup: {symbol}")
    print("=" * 40)
    
    try:
        ticker = Ticker(symbol)
        
        # Get all data types
        key_stats = ticker.key_stats
        financial_data = ticker.financial_data
        summary_detail = ticker.summary_detail
        
        if symbol in key_stats and isinstance(key_stats[symbol], dict):
            stats = key_stats[symbol]
            fin_data = financial_data.get(symbol, {}) if isinstance(financial_data.get(symbol), dict) else {}
            summary = summary_detail.get(symbol, {}) if isinstance(summary_detail.get(symbol), dict) else {}
            
            # Display key metrics
            print(f"Current Price: ${fin_data.get('currentPrice', 'N/A')}")
            print(f"Market Cap: ${summary.get('marketCap', 0):,.0f}" if summary.get('marketCap') else "Market Cap: N/A")
            print(f"Enterprise Value: ${stats.get('enterpriseValue', 0):,.0f}" if stats.get('enterpriseValue') else "Enterprise Value: N/A")
            print()
            
            print("VALUATION:")
            print(f"  Forward P/E: {stats.get('forwardPE', 'N/A')}")
            print(f"  Trailing EPS: {stats.get('trailingEps', 'N/A')}")
            print(f"  Price to Book: {stats.get('priceToBook', 'N/A')}")
            print()
            
            print("FINANCIAL HEALTH:")
            print(f"  Total Revenue: ${fin_data.get('totalRevenue', 0):,.0f}" if fin_data.get('totalRevenue') else "  Total Revenue: N/A")
            print(f"  EBITDA: ${fin_data.get('ebitda', 0):,.0f}" if fin_data.get('ebitda') else "  EBITDA: N/A")
            print(f"  Free Cash Flow: ${fin_data.get('freeCashflow', 0):,.0f}" if fin_data.get('freeCashflow') else "  Free Cash Flow: N/A")
            print(f"  Total Debt: ${fin_data.get('totalDebt', 0):,.0f}" if fin_data.get('totalDebt') else "  Total Debt: N/A")
            print()
            
            print("PROFITABILITY:")
            print(f"  ROE: {fin_data.get('returnOnEquity', 'N/A')}")
            print(f"  ROA: {fin_data.get('returnOnAssets', 'N/A')}")
            print(f"  Gross Margin: {fin_data.get('grossMargins', 'N/A')}")
            print(f"  Operating Margin: {fin_data.get('operatingMargins', 'N/A')}")
            print(f"  Profit Margin: {fin_data.get('profitMargins', 'N/A')}")
            print()
            
            print("LEVERAGE & LIQUIDITY:")
            print(f"  Debt/Equity: {fin_data.get('debtToEquity', 'N/A')}")
            print(f"  Current Ratio: {fin_data.get('currentRatio', 'N/A')}")
            print(f"  Quick Ratio: {fin_data.get('quickRatio', 'N/A')}")
            print()
            
            print("DIVIDENDS:")
            print(f"  Dividend Yield: {summary.get('dividendYield', 'N/A')}")
            print(f"  Payout Ratio: {summary.get('payoutRatio', 'N/A')}")
            
        else:
            print(f"No data found for {symbol}")
            
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")


def compare_symbols(symbols):
    """
    Quick comparison of multiple symbols
    """
    print(f"\nQuick Comparison: {', '.join(symbols)}")
    print("=" * 60)
    
    try:
        tickers = Ticker(symbols)
        financial_data = tickers.financial_data
        summary_detail = tickers.summary_detail
        key_stats = tickers.key_stats
        
        comparison_data = []
        
        for symbol in symbols:
            fin_data = financial_data.get(symbol, {}) if isinstance(financial_data.get(symbol), dict) else {}
            summary = summary_detail.get(symbol, {}) if isinstance(summary_detail.get(symbol), dict) else {}
            stats = key_stats.get(symbol, {}) if isinstance(key_stats.get(symbol), dict) else {}
            
            comparison_data.append({
                'Symbol': symbol,
                'Price': fin_data.get('currentPrice', None),
                'Market_Cap_B': round(summary.get('marketCap', 0) / 1e9, 1) if summary.get('marketCap') else None,
                'Forward_PE': stats.get('forwardPE', None),
                'ROE': fin_data.get('returnOnEquity', None),
                'Debt_Equity': fin_data.get('debtToEquity', None),
                'Current_Ratio': fin_data.get('currentRatio', None),
                'Profit_Margin': fin_data.get('profitMargins', None)
            })
        
        df = pd.DataFrame(comparison_data)
        print(df.to_string(index=False))
        
        return df
        
    except Exception as e:
        print(f"Error in comparison: {e}")
        return pd.DataFrame()


def main():
    """
    Interactive lookup tool
    """
    print("YAHOO FINANCE QUICK LOOKUP TOOL")
    print("=" * 50)
    
    # Example single lookups
    symbols_to_check = ['AAPL', 'TSLA', 'NVDA']
    
    for symbol in symbols_to_check:
        quick_lookup(symbol)
        print("\n" + "-" * 60 + "\n")
    
    # Quick comparison
    comparison_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA']
    compare_df = compare_symbols(comparison_symbols)
    
    # Save comparison
    if not compare_df.empty:
        compare_df.to_csv('quick_comparison.csv', index=False)
        print(f"\nComparison saved to: quick_comparison.csv")


# Interactive functions for manual use
def lookup(symbol):
    """Simple function to lookup any symbol"""
    quick_lookup(symbol.upper())

def compare(*symbols):
    """Simple function to compare multiple symbols"""
    symbol_list = [s.upper() for s in symbols]
    return compare_symbols(symbol_list)


if __name__ == "__main__":
    main()
    
    print("\n" + "=" * 60)
    print("MANUAL USAGE EXAMPLES:")
    print("=" * 60)
    print("# Look up single symbol:")
    print("lookup('AAPL')")
    print()
    print("# Compare multiple symbols:")
    print("compare('AAPL', 'MSFT', 'GOOGL')")
    print()
    print("# Just run the functions directly in Python console!")
