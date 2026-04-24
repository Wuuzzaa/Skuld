import pytest
import pandas as pd
import numpy as np
from src.spreads_calculation import calc_spreads, get_page_spreads

@pytest.fixture
def sample_spread_data():
    return pd.DataFrame({
        'symbol': ['AAPL', 'AAPL'],
        'expiration_date': ['2026-05-15', '2026-05-15'],
        'option_type': ['put', 'put'],
        'close': [150.0, 150.0],
        'sell_strike': [145.0, 145.0],
        'sell_last_option_price': [2.0, 2.0],
        'sell_delta': [0.3, 0.3],
        'sell_iv': [0.25, 0.25],
        'sell_theta': [-0.05, -0.05],
        'buy_strike': [140.0, 140.0],
        'buy_last_option_price': [1.0, 1.0],
        'buy_delta': [0.15, 0.15],
        'buy_theta': [-0.02, -0.02],
        'days_to_expiration': [30, 30],
        'earnings_date': ['2026-06-01', '2026-06-01']
    })

def test_calc_spreads_basic(sample_spread_data):
    result = calc_spreads(sample_spread_data)
    
    assert not result.empty
    assert 'max_profit' in result.columns
    assert 'bpr' in result.columns
    assert 'expected_value' in result.columns
    assert 'APDI' in result.columns
    
    # Check values for one row
    row = result.iloc[0]
    assert row['spread_width'] == 5.0
    assert row['max_profit'] == 100.0 # (2.0 - 1.0) * 100
    assert row['bpr'] == 400.0 # 5.0 * 100 - 100
    assert row['profit_to_bpr'] == 0.25

def test_calc_spreads_empty():
    result = calc_spreads(pd.DataFrame())
    assert result.empty

def test_get_page_spreads_filtering(sample_spread_data):
    # Add a row with negative profit
    bad_row = sample_spread_data.iloc[0:1].copy()
    bad_row['sell_last_option_price'] = 0.5
    bad_row['buy_last_option_price'] = 1.0
    
    data = pd.concat([sample_spread_data, bad_row])
    result = get_page_spreads(data)
    
    # The bad row should be filtered out because max_profit <= 0
    assert len(result) == 2 # Original rows were 2, added 1 bad = 3 total, result should be 2
