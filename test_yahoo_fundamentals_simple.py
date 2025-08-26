"""
Standalone script to fetch fundamental data directly from Yahoo Finance API
Using yahooquery only (no rate limiting issues)
"""

import pandas as pd
from yahooquery import Ticker
import time


def get_market_caps_yahooquery():
    """
    Get market caps for specific symbols using yahooquery
    """
    print("Market Cap Analysis using yahooquery:")
    print("=" * 50)
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META', 'AMZN', 'NFLX']
    
    try:
        # Create ticker object for multiple symbols
        tickers = Ticker(symbols)
        
        # Get key statistics (contains market cap)
        key_stats = tickers.key_stats
        
        market_caps = []
        
        for symbol in symbols:
            if symbol in key_stats and isinstance(key_stats[symbol], dict):
                stats = key_stats[symbol]
                
                # Calculate market cap from shares outstanding and current price
                shares_outstanding = stats.get('sharesOutstanding', None)
                
                # Get current price from summary detail
                summary = tickers.summary_detail
                current_price = None
                if symbol in summary and isinstance(summary[symbol], dict):
                    current_price = summary[symbol].get('previousClose', None)
                
                # Calculate market cap
                if shares_outstanding and current_price:
                    market_cap = shares_outstanding * current_price
                    market_caps.append({
                        'Symbol': symbol,
                        'Shares_Outstanding': shares_outstanding,
                        'Current_Price': current_price,
                        'Market_Cap': market_cap,
                        'Market_Cap_Billions': round(market_cap / 1e9, 2)
                    })
                else:
                    print(f"Missing data for {symbol}")
        
        # Create DataFrame and sort
        if market_caps:
            df = pd.DataFrame(market_caps)
            df = df.sort_values('Market_Cap', ascending=False)
            print(df.to_string(index=False))
            return df
        else:
            print("No market cap data found")
            return pd.DataFrame()
            
    except Exception as e:
        print(f"Error fetching market cap data: {e}")
        return pd.DataFrame()


def get_comprehensive_fundamentals():
    """
    Get comprehensive fundamental data using yahooquery
    """
    print("\n\nComprehensive Fundamental Analysis:")
    print("=" * 50)
    
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    
    try:
        tickers = Ticker(symbols)
        
        # Get different types of data
        key_stats = tickers.key_stats
        financial_data = tickers.financial_data
        summary_detail = tickers.summary_detail
        
        results = []
        
        for symbol in symbols:
            print(f"\n--- {symbol} Analysis ---")
            
            data = {'Symbol': symbol}
            
            # From key_stats
            if symbol in key_stats and isinstance(key_stats[symbol], dict):
                stats = key_stats[symbol]
                data['Enterprise_Value'] = stats.get('enterpriseValue', None)
                data['Forward_PE'] = stats.get('forwardPE', None)
                data['Trailing_PE'] = stats.get('trailingEps', None)
                data['Price_to_Book'] = stats.get('priceToBook', None)
                data['Shares_Outstanding'] = stats.get('sharesOutstanding', None)
                data['Beta'] = stats.get('beta', None)
                data['Book_Value'] = stats.get('bookValue', None)
            
            # From financial_data
            if symbol in financial_data and isinstance(financial_data[symbol], dict):
                fin_data = financial_data[symbol]
                data['Current_Price'] = fin_data.get('currentPrice', None)
                data['Total_Cash'] = fin_data.get('totalCash', None)
                data['Total_Debt'] = fin_data.get('totalDebt', None)
                data['Total_Revenue'] = fin_data.get('totalRevenue', None)
                data['EBITDA'] = fin_data.get('ebitda', None)
                data['Free_Cash_Flow'] = fin_data.get('freeCashflow', None)
                data['ROE'] = fin_data.get('returnOnEquity', None)
                data['ROA'] = fin_data.get('returnOnAssets', None)
                data['Debt_to_Equity'] = fin_data.get('debtToEquity', None)
                data['Current_Ratio'] = fin_data.get('currentRatio', None)
                data['Quick_Ratio'] = fin_data.get('quickRatio', None)
                data['Gross_Margins'] = fin_data.get('grossMargins', None)
                data['Operating_Margins'] = fin_data.get('operatingMargins', None)
                data['Profit_Margins'] = fin_data.get('profitMargins', None)
            
            # From summary_detail
            if symbol in summary_detail and isinstance(summary_detail[symbol], dict):
                summary = summary_detail[symbol]
                data['Market_Cap'] = summary.get('marketCap', None)
                data['Dividend_Yield'] = summary.get('dividendYield', None)
                data['Payout_Ratio'] = summary.get('payoutRatio', None)
                data['52_Week_High'] = summary.get('fiftyTwoWeekHigh', None)
                data['52_Week_Low'] = summary.get('fiftyTwoWeekLow', None)
            
            # Calculate additional metrics
            if data.get('Total_Revenue') and data.get('Market_Cap'):
                data['PS_Ratio'] = data['Market_Cap'] / data['Total_Revenue']
            
            if data.get('EBITDA') and data.get('Enterprise_Value'):
                data['EV_EBITDA'] = data['Enterprise_Value'] / data['EBITDA']
            
            results.append(data)
            
            # Print key metrics for this symbol
            print(f"Market Cap: ${data.get('Market_Cap', 0):,.0f}" if data.get('Market_Cap') else "Market Cap: N/A")
            print(f"Revenue: ${data.get('Total_Revenue', 0):,.0f}" if data.get('Total_Revenue') else "Revenue: N/A")
            print(f"P/E Ratio: {data.get('Forward_PE', 'N/A')}")
            print(f"ROE: {data.get('ROE', 'N/A')}")
            print(f"Debt/Equity: {data.get('Debt_to_Equity', 'N/A')}")
        
        # Create comprehensive DataFrame
        df = pd.DataFrame(results)
        
        print(f"\n\nFull dataset shape: {df.shape}")
        print("Columns available:", list(df.columns))
        
        return df
        
    except Exception as e:
        print(f"Error in comprehensive analysis: {e}")
        return pd.DataFrame()


def get_specific_metric(symbols, metric_name):
    """
    Get a specific metric for multiple symbols
    """
    print(f"\n\nSpecific Metric Analysis: {metric_name}")
    print("=" * 50)
    
    try:
        tickers = Ticker(symbols)
        financial_data = tickers.financial_data
        
        results = []
        
        for symbol in symbols:
            if symbol in financial_data and isinstance(financial_data[symbol], dict):
                value = financial_data[symbol].get(metric_name, None)
                results.append({
                    'Symbol': symbol,
                    metric_name: value
                })
            else:
                results.append({
                    'Symbol': symbol,
                    metric_name: None
                })
        
        df = pd.DataFrame(results)
        print(df.to_string(index=False))
        return df
        
    except Exception as e:
        print(f"Error fetching {metric_name}: {e}")
        return pd.DataFrame()


def compare_pe_ratios():
    """
    Compare P/E ratios across symbols
    """
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'META']
    
    print("\n\nP/E Ratio Comparison:")
    print("=" * 30)
    
    try:
        tickers = Ticker(symbols)
        key_stats = tickers.key_stats
        
        pe_data = []
        
        for symbol in symbols:
            if symbol in key_stats and isinstance(key_stats[symbol], dict):
                stats = key_stats[symbol]
                trailing_pe = None
                forward_pe = stats.get('forwardPE', None)
                
                # Calculate trailing PE from EPS
                trailing_eps = stats.get('trailingEps', None)
                if trailing_eps and trailing_eps > 0:
                    # Get current price
                    summary = tickers.summary_detail
                    if symbol in summary and isinstance(summary[symbol], dict):
                        current_price = summary[symbol].get('previousClose', None)
                        if current_price:
                            trailing_pe = current_price / trailing_eps
                
                pe_data.append({
                    'Symbol': symbol,
                    'Trailing_PE': trailing_pe,
                    'Forward_PE': forward_pe,
                    'PE_Difference': (trailing_pe - forward_pe) if (trailing_pe and forward_pe) else None
                })
        
        df = pd.DataFrame(pe_data)
        df = df.sort_values('Forward_PE', ascending=True)
        print(df.to_string(index=False))
        return df
        
    except Exception as e:
        print(f"Error comparing P/E ratios: {e}")
        return pd.DataFrame()


def main():
    """
    Main function to run all analyses
    """
    print("YAHOO FINANCE FUNDAMENTAL DATA TESTING (yahooquery only)")
    print("=" * 70)
    
    # Market cap analysis
    market_caps_df = get_market_caps_yahooquery()
    
    # Comprehensive fundamentals
    fundamentals_df = get_comprehensive_fundamentals()
    
    # Specific metrics
    symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA']
    
    # Market cap specifically
    market_cap_df = get_specific_metric(symbols, 'currentPrice')
    
    # P/E comparison
    pe_df = compare_pe_ratios()
    
    # Save results
    if not fundamentals_df.empty:
        fundamentals_df.to_csv('yahooquery_fundamentals_test.csv', index=False)
        print(f"\n\nSaved comprehensive data to: yahooquery_fundamentals_test.csv")
    
    if not market_caps_df.empty:
        market_caps_df.to_csv('yahooquery_market_caps.csv', index=False)
        print(f"Saved market cap data to: yahooquery_market_caps.csv")
    
    print(f"\nAnalysis complete!")


if __name__ == "__main__":
    main()
