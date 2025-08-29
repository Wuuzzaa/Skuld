import yfinance as yf
import pandas as pd
import numpy as np
import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import get_filtered_symbols_with_logging


def check_dividend_stability(ticker, years=10):
    """
    Comprehensive dividend stability check for married put strategies.
    
    Returns dict with stability metrics and classification.
    """
    try:
        # --- 1) Load data ---
        tk = yf.Ticker(ticker)
        
        # Dividends (Date -> Amount per share)
        div = tk.dividends
        if div is None or len(div) == 0:
            return create_failed_result(ticker, "No dividends found")
        
        # Financial data for payout analysis
        financials = tk.financials
        cashflow = tk.cashflow
        
        # --- 2) Limit time horizon ---
        cutoff_date = datetime.now() - timedelta(days=years*365)
        
        # Handle timezone-aware dividend data
        if div.index.tz is not None:
            # Convert cutoff_date to same timezone as dividend data
            import pytz
            cutoff_date = pytz.timezone('America/New_York').localize(cutoff_date.replace(tzinfo=None))
        
        div = div[div.index >= cutoff_date]
        
        # Create timezone-aware timedelta for comparison
        cutoff_plus_180 = cutoff_date + timedelta(days=180)
        
        if div.empty or (div.index.min() > cutoff_plus_180):
            return create_failed_result(ticker, "Insufficient dividend history")
        
        # --- 3) Frequency & Continuity ---
        # Annual dividend sums and payment counts
        div_year = div.resample('YE').sum()
        pay_count_year = div.resample('YE').count()
        
        # Regularity: % of years with ≥1 payment
        years_with_div = (pay_count_year > 0).sum()
        regularity_ratio = years_with_div / len(div_year) if len(div_year) > 0 else 0
        
        # Payment frequency (quarterly ≈ 4, semi-annual ≈ 2, annual ≈ 1)
        median_freq = pay_count_year[pay_count_year > 0].median() if (pay_count_year > 0).any() else 0
        
        # --- 4) Cuts & Streak ---
        # YoY growth of annual dividend sum
        yoy = div_year.pct_change()
        # Cuts: YoY < -10% (tolerating small fluctuations)
        cuts = (yoy < -0.10).sum()
        
        # Streak of increasing/stable dividends (tolerant to ±1%)
        div_diff = div_year.diff()
        streak = calculate_longest_streak(div_diff >= -0.01)
        
        # --- 5) Volatility & CAGR ---
        # Volatility of annual dividends (lower = more stable)
        if len(div_year[div_year > 0]) > 1:
            vol = np.std(np.log(div_year[div_year > 0]))
        else:
            vol = None
            
        # CAGR over entire period - only use complete years
        current_year = datetime.now().year
        complete_years = div_year[div_year.index.year < current_year]  # Exclude current incomplete year
        
        # Also exclude first year if it's incomplete (less than 4 quarters of data)
        if len(complete_years) > 0:
            first_year = complete_years.index[0].year
            first_year_payments = div[div.index.year == first_year]
            if len(first_year_payments) < 3:  # Less than 3 quarters -> incomplete
                complete_years = complete_years.iloc[1:]  # Skip first incomplete year
        
        if len(complete_years) > 1 and complete_years.iloc[0] > 0:
            years_span = len(complete_years) - 1
            cagr = (complete_years.iloc[-1] / complete_years.iloc[0]) ** (1 / max(1, years_span)) - 1
        else:
            cagr = None
        
        # --- 6) Dividend Frequency Analysis ---
        # Determine actual payment frequency based on historical patterns
        frequency_analysis = analyze_dividend_frequency(div, pay_count_year)
        
        # --- 7) Payout Quality Analysis ---
        payout_analysis = analyze_payout_quality(financials, cashflow, div_year)
        
        # --- 8) Scoring Logic ---
        score = 0
        reasons = []
        
        # Extract analysis results
        payout_ok_ratio = payout_analysis["payout_ratio_stable"]
        fcf_ok_ratio = payout_analysis["fcf_coverage_adequate"]
        
        # Minimum criteria
        if regularity_ratio >= 0.9:
            score += 1
            reasons.append("Regular payments (≥90% of years)")
        elif regularity_ratio >= 0.7:
            score += 0.5
            reasons.append("Mostly regular payments")
        else:
            reasons.append("Irregular payments")
        
        if cuts == 0:
            score += 1
            reasons.append("No YoY cuts")
        elif cuts <= 1:
            score += 0.5
            reasons.append("Minor cuts tolerated")
        else:
            reasons.append("Multiple cuts")
        
        if streak >= (years - 1):
            score += 1
            reasons.append("Nearly continuous streak")
        elif streak >= int(years * 0.6):
            score += 0.5
            reasons.append("Solid streak")
        else:
            reasons.append("Short streak")
        
        if vol is not None and vol <= 0.25:
            score += 1
            reasons.append("Low dividend volatility")
        elif vol is not None and vol <= 0.40:
            score += 0.5
            reasons.append("Acceptable volatility")
        else:
            reasons.append("High volatility")
        
        if cagr is not None and cagr >= 0.02:
            score += 1
            reasons.append("Positive dividend growth (≥2% p.a.)")
        elif cagr is not None and cagr >= 0.00:
            score += 0.5
            reasons.append("Stable without growth")
        else:
            reasons.append("Declining dividends")
        
        # Payout quality (placeholder for now)
        if payout_ok_ratio is None:
            reasons.append("Payout ratio not analyzable")
        elif payout_ok_ratio >= 0.6:
            score += 1
            reasons.append("Sustainable payout ratio")
        else:
            reasons.append("High payout ratio concern")
        
        # --- 8) Final Classification ---
        if score >= 5:
            label = "STABLE"
        elif score >= 3.5:
            label = "OK_CHECK_REQUIRED"
        else:
            label = "NOT_STABLE"
        
        return {
            "symbol": ticker,
            "dividend_stability_label": label,
            "dividend_stability_score": score,
            "dividend_regularity_ratio": round(regularity_ratio, 3),
            "median_payments_per_year": round(median_freq, 1),
            "dividend_frequency_type": frequency_analysis["frequency_type"],
            "dividend_frequency_consistency": frequency_analysis["frequency_consistency"],
            "dividend_cuts_count": int(cuts),
            "dividend_streak_years": int(streak),
            "dividend_cagr": round(cagr, 4) if cagr is not None else None,
            "dividend_volatility": round(vol, 4) if vol is not None else None,
            "years_analyzed": len(div_year),
            "payout_ratio_stable": payout_ok_ratio,
            "fcf_coverage_adequate": fcf_ok_ratio,
            "earnings_coverage": payout_analysis.get("earnings_coverage"),
            "analysis_notes": "; ".join(reasons)
        }
        
    except Exception as e:
        return create_failed_result(ticker, f"Analysis error: {str(e)}")


def create_failed_result(ticker, reason):
    """Create standardized failed result"""
    return {
        "symbol": ticker,
        "dividend_stability_label": "ANALYSIS_FAILED",
        "dividend_stability_score": 0,
        "dividend_regularity_ratio": None,
        "median_payments_per_year": None,
        "dividend_frequency_type": "Unknown",
        "dividend_frequency_consistency": None,
        "dividend_cuts_count": None,
        "dividend_streak_years": None,
        "dividend_cagr": None,
        "dividend_volatility": None,
        "years_analyzed": 0,
        "payout_ratio_stable": None,
        "fcf_coverage_adequate": None,
        "earnings_coverage": None,
        "analysis_notes": reason
    }


def analyze_dividend_frequency(div, pay_count_year):
    """
    Analyze dividend payment frequency patterns.
    Returns frequency type and consistency metrics.
    """
    if pay_count_year.empty:
        return {
            "frequency_type": "None",
            "frequency_consistency": 0,
            "avg_payments_per_year": 0
        }
    
    # Calculate average payments per year (excluding zero years)
    non_zero_payments = pay_count_year[pay_count_year > 0]
    if len(non_zero_payments) == 0:
        return {
            "frequency_type": "None", 
            "frequency_consistency": 0,
            "avg_payments_per_year": 0
        }
    
    avg_payments = non_zero_payments.mean()
    
    # Determine frequency type based on average
    if avg_payments >= 3.5:
        frequency_type = "Quarterly"
        expected = 4
    elif avg_payments >= 1.5:
        frequency_type = "Semi-annual"
        expected = 2
    elif avg_payments >= 0.8:
        frequency_type = "Annual"
        expected = 1
    else:
        frequency_type = "Irregular"
        expected = avg_payments
    
    # Calculate consistency (how often actual payments match expected pattern)
    if expected > 0:
        consistency = 1 - abs(non_zero_payments - expected).mean() / expected
        consistency = max(0, min(1, consistency))  # Clamp between 0-1
    else:
        consistency = 0
    
    return {
        "frequency_type": frequency_type,
        "frequency_consistency": round(consistency, 3),
        "avg_payments_per_year": round(avg_payments, 2)
    }


def analyze_payout_quality(financials, cashflow, div_year):
    """
    Analyze dividend payout sustainability using financial data.
    Returns payout ratios and coverage metrics.
    """
    result = {
        "payout_ratio_stable": None,
        "fcf_coverage_adequate": None,
        "earnings_coverage": None
    }
    
    try:
        # Earnings-based payout analysis
        if not financials.empty and 'Net Income' in financials.index:
            net_income = financials.loc['Net Income'].dropna()
            
            # Align with dividend years (approximate)
            years_overlap = min(len(div_year), len(net_income))
            if years_overlap >= 3:
                recent_ni = net_income.tail(years_overlap)
                recent_div = div_year.tail(years_overlap)
                
                # Calculate payout ratios (need shares outstanding for precise calculation)
                # This is simplified - assumes total dividends vs net income
                payout_ratios = []
                for i in range(len(recent_div)):
                    if recent_ni.iloc[i] > 0:
                        # Approximate: dividend per share * estimated shares
                        # This is very rough without shares data
                        payout_ratio = min(5.0, recent_div.iloc[i] * 1000000000 / recent_ni.iloc[i])  # Rough estimate
                        payout_ratios.append(payout_ratio)
                
                if payout_ratios:
                    stable_ratios = [r for r in payout_ratios if r <= 0.65]
                    result["payout_ratio_stable"] = len(stable_ratios) / len(payout_ratios)
                    result["earnings_coverage"] = np.mean([1/r for r in payout_ratios if r > 0])
        
        # Cash flow analysis
        if not cashflow.empty and 'Free Cash Flow' in cashflow.index:
            fcf = cashflow.loc['Free Cash Flow'].dropna()
            
            # This would need dividend payments from cash flow statement
            # For now, return placeholder
            result["fcf_coverage_adequate"] = 0.7  # Placeholder
            
    except Exception as e:
        print(f"Warning: Payout analysis failed: {e}")
    
    return result


def calculate_longest_streak(boolean_series):
    """Calculate longest consecutive True streak in boolean series"""
    if boolean_series.empty:
        return 0
    
    streak = 0
    max_streak = 0
    
    for val in boolean_series:
        if val:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    
    return max_streak


def generate_dividend_stability_analysis():
    """
    Main function to analyze dividend stability for all symbols.
    Called from main.py after fundamental data collection.
    """
    print("🔍 Analyzing dividend stability for married put strategies...")
    
    symbols = get_filtered_symbols_with_logging("Dividend Stability Analysis")
    
    all_stability_data = []
    
    for symbol in symbols:
        print(f"Analyzing dividend stability for {symbol}...")
        
        try:
            stability_data = check_dividend_stability(symbol, years=10)
            all_stability_data.append(stability_data)
            
            # Log result
            label = stability_data["dividend_stability_label"]
            score = stability_data["dividend_stability_score"]
            print(f"  {symbol}: {label} (Score: {score}/7)")
            
        except Exception as e:
            print(f"  Error analyzing {symbol}: {e}")
            all_stability_data.append(create_failed_result(symbol, str(e)))
    
    if not all_stability_data:
        print("No dividend stability data collected")
        return
    
    # Create DataFrame
    df_stability = pd.DataFrame(all_stability_data)
    
    # Save results
    stability_path = PATH_DATA / 'dividend_stability_analysis.feather'
    df_stability.to_feather(stability_path)
    
    print(f"Dividend stability analysis saved: {stability_path}")
    print(f"Analyzed {len(df_stability)} symbols")
    
    # Summary stats
    stable_count = (df_stability['dividend_stability_label'] == 'STABLE').sum()
    ok_count = (df_stability['dividend_stability_label'] == 'OK_CHECK_REQUIRED').sum()
    unstable_count = (df_stability['dividend_stability_label'] == 'NOT_STABLE').sum()
    
    print(f"Results: {stable_count} STABLE, {ok_count} OK, {unstable_count} NOT_STABLE")
    
    return df_stability


if __name__ == "__main__":
    # Test with single symbol
    result = check_dividend_stability('AAPL')
    print("Test result for AAPL:")
    for key, value in result.items():
        print(f"  {key}: {value}")
