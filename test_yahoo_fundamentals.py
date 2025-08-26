"""
Test script to fetch fundamental data directly from Yahoo Finance API
This is a standalone script for testing and exploring fundamental data
"""

import pandas as pd
import yfinance as yf
from yahooquery import Ticker
import time


def test_yfinance_fundamentals():
    """
    Test fundamental data fetching with yfinance library
    """
    print("Testing yfinance library:")
    print("=" * 50)
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    
    for symbol in symbols:
        print(f"\n--- {symbol} ---")
        
        try:
            # Create ticker object
            ticker = yf.Ticker(symbol)
            
            # Get basic info
            info = ticker.info
            
            # Extract key fundamentals
            market_cap = info.get('marketCap', 'N/A')
            pe_ratio = info.get('trailingPE', 'N/A')
            forward_pe = info.get('forwardPE', 'N/A')
            price_to_book = info.get('priceToBook', 'N/A')
            debt_to_equity = info.get('debtToEquity', 'N/A')
            roe = info.get('returnOnEquity', 'N/A')
            revenue = info.get('totalRevenue', 'N/A')
            
            print(f"Market Cap: {market_cap:,}" if isinstance(market_cap, (int, float)) else f"Market Cap: {market_cap}")
            print(f"P/E Ratio: {pe_ratio}")
            print(f"Forward P/E: {forward_pe}")
            print(f"Price to Book: {price_to_book}")
            print(f"Debt to Equity: {debt_to_equity}")
            print(f"ROE: {roe}")
            print(f"Total Revenue: {revenue:,}" if isinstance(revenue, (int, float)) else f"Total Revenue: {revenue}")
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
        
        time.sleep(0.5)  # Rate limiting


def test_yahooquery_fundamentals():
    """
    Test fundamental data fetching with yahooquery library
    """
    print("\n\nTesting yahooquery library:")
    print("=" * 50)
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    
    try:
        # Create ticker object for multiple symbols
        tickers = Ticker(symbols)
        
        # Get key statistics
        key_stats = tickers.key_stats
        print("\nKey Statistics:")
        print(key_stats)
        
        # Get valuation measures
        valuation = tickers.valuation_measures
        print("\nValuation Measures:")
        print(valuation)
        
        # Get financial data
        financial_data = tickers.financial_data
        print("\nFinancial Data:")
        print(financial_data)
        
        # Get summary detail
        summary_detail = tickers.summary_detail
        print("\nSummary Detail:")
        print(summary_detail)
        
    except Exception as e:
        print(f"Error fetching yahooquery data: {e}")


def get_specific_fundamentals(symbols):
    """
    Get specific fundamental metrics for given symbols
    """
    print("\n\nSpecific Fundamental Metrics:")
    print("=" * 50)
    
    results = []
    
    for symbol in symbols:
        try:
            # yfinance approach
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Extract specific metrics
            data = {
                'Symbol': symbol,
                'Market_Cap': info.get('marketCap', None),
                'Enterprise_Value': info.get('enterpriseValue', None),
                'PE_Ratio': info.get('trailingPE', None),
                'Forward_PE': info.get('forwardPE', None),
                'PB_Ratio': info.get('priceToBook', None),
                'PS_Ratio': info.get('priceToSalesTrailing12Months', None),
                'Debt_to_Equity': info.get('debtToEquity', None),
                'ROE': info.get('returnOnEquity', None),
                'ROA': info.get('returnOnAssets', None),
                'Total_Revenue': info.get('totalRevenue', None),
                'EBITDA': info.get('ebitda', None),
                'Free_Cash_Flow': info.get('freeCashflow', None),
                'Current_Ratio': info.get('currentRatio', None),
                'Quick_Ratio': info.get('quickRatio', None),
                'Dividend_Yield': info.get('dividendYield', None),
                'Payout_Ratio': info.get('payoutRatio', None)
            }
            
            results.append(data)
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
        
        time.sleep(0.3)  # Rate limiting
    
    # Convert to DataFrame
    df = pd.DataFrame(results)
    
    # Display results
    print(df.to_string(index=False))
    
    return df


def compare_market_caps():
    """
    Compare market caps across different symbols
    """
    print("\n\nMarket Cap Comparison:")
    print("=" * 50)
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN']
    
    market_caps = []
    
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            market_cap = info.get('marketCap', None)
            
            if market_cap:
                market_caps.append({
                    'Symbol': symbol,
                    'Market_Cap': market_cap,
                    'Market_Cap_Billions': round(market_cap / 1e9, 2)
                })
            
        except Exception as e:
            print(f"Error fetching market cap for {symbol}: {e}")
        
        time.sleep(0.2)
    
    # Sort by market cap
    market_caps_df = pd.DataFrame(market_caps)
    market_caps_df = market_caps_df.sort_values('Market_Cap', ascending=False)
    
    print(market_caps_df.to_string(index=False))
    
    return market_caps_df


def test_yahoo_query_detailed():
    """
    Detailed test of yahooquery for specific fundamental metrics
    """
    print("\n\nDetailed yahooquery test:")
    print("=" * 50)
    
    symbols = ['AAPL', 'MSFT']
    
    for symbol in symbols:
        print(f"\n--- {symbol} Detailed Analysis ---")
        
        try:
            ticker = Ticker(symbol)
            
            # Income statement
            income_stmt = ticker.income_statement()
            if not income_stmt.empty:
                print("Latest Annual Income Statement (key items):")
                latest_annual = income_stmt[income_stmt['periodType'] == 'annual'].iloc[-1]
                print(f"  Total Revenue: {latest_annual.get('TotalRevenue', 'N/A'):,}")
                print(f"  Net Income: {latest_annual.get('NetIncome', 'N/A'):,}")
                print(f"  EBITDA: {latest_annual.get('EBITDA', 'N/A'):,}")
            
            # Balance sheet
            balance_sheet = ticker.balance_sheet()
            if not balance_sheet.empty:
                print("Latest Annual Balance Sheet (key items):")
                latest_bs = balance_sheet[balance_sheet['periodType'] == 'annual'].iloc[-1]
                print(f"  Total Assets: {latest_bs.get('TotalAssets', 'N/A'):,}")
                print(f"  Total Debt: {latest_bs.get('TotalDebt', 'N/A'):,}")
                print(f"  Stockholders Equity: {latest_bs.get('StockholdersEquity', 'N/A'):,}")
            
            # Cash flow
            cash_flow = ticker.cash_flow()
            if not cash_flow.empty:
                print("Latest Annual Cash Flow (key items):")
                latest_cf = cash_flow[cash_flow['periodType'] == 'annual'].iloc[-1]
                print(f"  Operating Cash Flow: {latest_cf.get('OperatingCashFlow', 'N/A'):,}")
                print(f"  Free Cash Flow: {latest_cf.get('FreeCashFlow', 'N/A'):,}")
            
        except Exception as e:
            print(f"Error in detailed analysis for {symbol}: {e}")


def main():
    """
    Main function to run all tests
    """
    print("YAHOO FINANCE FUNDAMENTAL DATA TESTING")
    print("=" * 60)
    
    # Test different approaches
    test_yfinance_fundamentals()
    test_yahooquery_fundamentals()
    
    # Get specific metrics
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    df = get_specific_fundamentals(symbols)
    
    # Compare market caps
    market_caps_df = compare_market_caps()
    
    # Detailed yahooquery test
    test_yahoo_query_detailed()
    
    # Save results to CSV for further analysis
    df.to_csv('fundamental_data_test.csv', index=False)
    market_caps_df.to_csv('market_cap_comparison.csv', index=False)
    
    print(f"\n\nResults saved to:")
    print("- fundamental_data_test.csv")
    print("- market_cap_comparison.csv")


if __name__ == "__main__":
    main()
