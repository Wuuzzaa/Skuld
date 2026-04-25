import pytest
import pandas as pd
import numpy as np
from src.iron_condor_calculation import calc_iron_condors, get_page_iron_condors

@pytest.fixture
def sample_ic_data():
    put_data = pd.DataFrame({
        'symbol': ['MSFT'],
        'expiration_date': ['2026-05-15'],
        'option_type': ['put'],
        'close': [400.0],
        'sell_strike': [380.0],
        'sell_last_option_price': [5.0],
        'sell_delta': [0.15],
        'sell_iv': [0.3],
        'sell_theta': [-0.1],
        'sell_open_interest': [1000],
        'buy_strike': [375.0],
        'buy_last_option_price': [3.0],
        'buy_delta': [0.1],
        'buy_theta': [-0.05],
        'buy_open_interest': [500],
        'days_to_expiration': [30],
        'earnings_date': ['2026-06-01'],
        'company_name': ['Microsoft']
    })
    
    call_data = pd.DataFrame({
        'symbol': ['MSFT'],
        'expiration_date': ['2026-05-15'],
        'option_type': ['call'],
        'close': [400.0],
        'sell_strike': [420.0],
        'sell_last_option_price': [4.0],
        'sell_delta': [0.15],
        'sell_iv': [0.28],
        'sell_theta': [-0.08],
        'sell_open_interest': [800],
        'buy_strike': [425.0],
        'buy_last_option_price': [2.5],
        'buy_delta': [0.1],
        'buy_theta': [-0.04],
        'buy_open_interest': [400],
        'days_to_expiration': [30],
        'earnings_date': ['2026-06-01'],
        'company_name': ['Microsoft']
    })
    
    return put_data, call_data

def test_calc_iron_condors_basic(sample_ic_data):
    puts, calls = sample_ic_data
    result = calc_iron_condors(puts, calls)
    
    assert not result.empty
    assert 'max_profit' in result.columns
    assert 'bpr' in result.columns
    assert 'sell_iv' in result.columns
    
    row = result.iloc[0]
    # Max Profit = (5-3 + 4-2.5) * 100 = (2 + 1.5) * 100 = 350
    assert row['max_profit'] == 350.0
    # Widths: Put side = 5, Call side = 5. Max = 5. 
    # BPR = 5 * 100 - 350 = 500 - 350 = 150
    assert row['bpr'] == 150.0
    # Sell IV = (0.3 + 0.28) / 2 = 0.29
    assert row['sell_iv'] == pytest.approx(0.29)
    
    # Total Theta
    # Put side: short -0.1, long -0.05 -> (-1*-0.1) + (1*-0.05) = 0.1 - 0.05 = 0.05
    # Call side: short -0.08, long -0.04 -> (-1*-0.08) + (1*-0.04) = 0.08 - 0.04 = 0.04
    # Strategy Theta = 0.05 + 0.04 = 0.09
    assert row['total_theta'] == pytest.approx(0.09)

def test_get_page_iron_condors_columns(sample_ic_data):
    puts, calls = sample_ic_data
    result = get_page_iron_condors(calc_iron_condors(puts, calls))
    
    assert 'days_to_expiration' in result.columns
    assert 'days_to_earnings' in result.columns
    assert 'Company' in result.columns
    assert result.iloc[0]['Company'] == 'Microsoft'
