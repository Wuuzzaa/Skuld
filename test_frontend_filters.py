"""
Frontend Filter Interface Test
Demonstrates how the filtering system would work in a web interface
"""

import pandas as pd
from src.married_put_calculation import get_married_puts


"""
Frontend Filter Interface Test
Demonstrates how the filtering system would work in a web interface
"""

import pandas as pd
from src.married_put_calculation import get_married_puts


def demo_frontend_interface():
    """
    Demo of how frontend interface would work with filter system
    """
    print("MARRIED PUT STRATEGY SCREENER - Frontend Demo")
    print("=" * 60)
    
    # Load data
    df = pd.read_feather('data/merged_df.feather')
    print(f"Loaded data: {df.shape[0]} options across {df['symbol'].nunique()} symbols")
    print()
    
    # Available expiration dates
    exp_dates = sorted(df['expiration_date'].unique())
    print(f"Available expirations: {exp_dates}")
    print()
    
    # Demo Filter Scenarios
    filter_scenarios = {
        "Conservative Income": {
            "description": "Large caps, low volatility, moderate delta",
            "filters": {
                "options": {
                    "delta_min": 0.20,
                    "delta_max": 0.35,
                    "iv_max": 50
                },
                "fundamentals": {
                    "MarketCap_min": 10_000_000_000,  # $10B+ 
                    "PE_Ratio_max": 30
                },
                "technicals": {
                    "RSI_min": 30,
                    "RSI_max": 70
                }
            }
        },
        
        "Value Hunting": {
            "description": "Undervalued stocks with good protection",
            "filters": {
                "options": {
                    "delta_min": 0.25,
                    "delta_max": 0.45
                },
                "fundamentals": {
                    "PE_Ratio_max": 20,
                    "ROE_Fund_min": 0.10,
                    "DebtEquity_Ratio_max": 1.0
                },
                "technicals": {
                    "RSI_max": 50  # Oversold
                }
            }
        },
        
        "High Income": {
            "description": "Higher premium collection, accepting more risk",
            "filters": {
                "options": {
                    "delta_min": 0.35,
                    "delta_max": 0.50,
                    "iv_min": 30
                },
                "fundamentals": {
                    "MarketCap_min": 1_000_000_000  # $1B+
                }
            }
        }
    }
    
    # Test each scenario
    for scenario_name, scenario in filter_scenarios.items():
        print(f"SCENARIO: {scenario_name}")
        print(f"   {scenario['description']}")
        
        # Apply filters and get results
        results = get_married_puts(df, exp_dates[0], scenario['filters'])
        
        if len(results) > 0:
            print(f"   Found {len(results)} opportunities")
            
            # Show top 3 results
            top_3 = results.head(3)
            print("   TOP 3 BY ROI SCORE:")
            for idx, row in top_3.iterrows():
                print(f"      {row['symbol']:>4} | Strike: ${row['strike']:>6.0f} | "
                      f"Delta: {row['delta']:>5.2f} | ROI: {row['roi_score']:>6.1f} | "
                      f"Protection: {row['protection_level_floor_pct']:>5.1f}%")
        else:
            print("   No results found with these criteria")
        
        print()
    
    print("FRONTEND INTERFACE ELEMENTS:")
    print("=" * 40)
    print("Filter Tabs:")
    print("   • Options (Delta, IV, Strike, Bid/Ask)")
    print("   • Technicals (RSI, MACD, ADX, Stoch)")  
    print("   • Fundamentals (PE, MarketCap, ROE, Debt/Equity)")
    print("   • Liquidity (Volume, Spread)")
    print()
    print("Filter Controls:")
    print("   • Range sliders (min/max)")
    print("   • Dropdown selections")
    print("   • Checkbox filters")
    print()
    print("Results Display:")
    print("   • Sortable table with all KPIs")
    print("   • Real-time filtering")
    print("   • Export functionality")
    print("   • Risk/return visualizations")


def show_available_filter_options():
    """
    Show all available filter options for frontend development
    """
    df = pd.read_feather('data/merged_df.feather')
    
    print("\nCOMPLETE FILTER OPTIONS FOR FRONTEND")
    print("=" * 50)
    
    filter_categories = {
        "Options": {
            "delta": {"type": "range", "current_range": [df['delta'].min(), df['delta'].max()]},
            "iv": {"type": "range", "current_range": [df['iv'].min(), df['iv'].max()]},
            "strike": {"type": "range", "current_range": [df['strike'].min(), df['strike'].max()]},
            "bid": {"type": "range", "current_range": [df['bid'].min(), df['bid'].max()]},
            "ask": {"type": "range", "current_range": [df['ask'].min(), df['ask'].max()]},
            "theta": {"type": "range", "current_range": [df['theta'].min(), df['theta'].max()]},
        },
        
        "Technicals": {
            "RSI": {"type": "range", "current_range": [df['RSI'].min(), df['RSI'].max()], "typical": [20, 80]},
            "ADX": {"type": "range", "current_range": [df['ADX'].min(), df['ADX'].max()]},
            "MACD.macd": {"type": "range", "current_range": [df['MACD.macd'].min(), df['MACD.macd'].max()]},
            "Stoch.K": {"type": "range", "current_range": [df['Stoch.K'].min(), df['Stoch.K'].max()]},
        },
        
        "Fundamentals": {
            "MarketCap": {"type": "range", "current_range": [df['MarketCap'].min(), df['MarketCap'].max()], "format": "currency"},
            "PE_Ratio": {"type": "range", "current_range": [df['PE_Ratio'].min(), df['PE_Ratio'].max()]},
            "ROE_Fund": {"type": "range", "current_range": [df['ROE_Fund'].min(), df['ROE_Fund'].max()], "format": "percentage"},
            "EBITDA": {"type": "range", "current_range": [df['EBITDA'].min(), df['EBITDA'].max()], "format": "currency"},
            "DebtEquity_Ratio": {"type": "range", "current_range": [df['DebtEquity_Ratio'].min(), df['DebtEquity_Ratio'].max()]},
        }
    }
    
    for category, fields in filter_categories.items():
        print(f"\n{category.upper()} FILTERS:")
        for field, config in fields.items():
            if field in df.columns:
                range_info = config['current_range']
                print(f"   {field:>15}: [{range_info[0]:>8.2f}, {range_info[1]:>8.2f}]")


if __name__ == "__main__":
    demo_frontend_interface()
    show_available_filter_options()
