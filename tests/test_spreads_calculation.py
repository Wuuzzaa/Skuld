import pytest
import pandas as pd
import numpy as np
from src.spreads_calculation import calc_spreads, get_page_spreads

@pytest.fixture
def sample_credit_spread_data():
    return pd.DataFrame({
        'symbol': ['AAPL'],
        'expiration_date': ['2026-05-15'],
        'option_type': ['put'],
        'close': [150.0],
        'sell_strike': [145.0],
        'sell_last_option_price': [2.0],
        'sell_delta': [0.3],
        'sell_iv': [0.25],
        'sell_theta': [-0.05],
        'buy_strike': [140.0],
        'buy_last_option_price': [1.0],
        'buy_delta': [0.15],
        'buy_theta': [-0.02],
        'days_to_expiration': [30],
        'earnings_date': ['2026-06-01']
    })

@pytest.fixture
def sample_debit_spread_data():
    # Bull Call Debit Spread
    # Buy Call 150 (sell_strike in SQL), Sell Call 155 (buy_strike in SQL)
    return pd.DataFrame({
        'symbol': ['MSFT'],
        'expiration_date': ['2026-05-15'],
        'option_type': ['call'],
        'close': [152.0],
        'sell_strike': [150.0], # "Target" (Long)
        'sell_last_option_price': [5.0],
        'sell_delta': [0.6],
        'sell_iv': [0.20],
        'sell_theta': [-0.08],
        'buy_strike': [155.0], # "Offset" (Short)
        'buy_last_option_price': [2.0],
        'buy_delta': [0.3],
        'buy_theta': [-0.05],
        'days_to_expiration': [30],
        'earnings_date': ['2026-06-01']
    })

def test_calc_spreads_credit(sample_credit_spread_data):
    result = calc_spreads(sample_credit_spread_data, strategy_type='credit')
    
    assert not result.empty
    row = result.iloc[0]
    assert row['spread_width'] == 5.0
    assert row['max_profit'] == 100.0 # (2.0 - 1.0) * 100
    assert row['bpr'] == 400.0 # 5.0 * 100 - 100
    assert row['spread_theta'] == pytest.approx(0.03) # sell_theta (short) * -1 + buy_theta (long) * 1 = -(-0.05) + (-0.02) = 0.03

def test_calc_spreads_debit(sample_debit_spread_data):
    result = calc_spreads(sample_debit_spread_data, strategy_type='debit')
    
    assert not result.empty
    row = result.iloc[0]
    assert row['spread_width'] == 5.0
    assert row['max_loss'] == 300.0 # (5.0 - 2.0) * 100
    assert row['max_profit'] == 200.0 # 5.0 * 100 - 300
    assert row['bpr'] == 300.0
    # Debit Theta: 
    # Long Leg (sell_strike 150): theta -0.08
    # Short Leg (buy_strike 155): theta -0.05
    # Strategy Theta = (1 * -0.08) + (-1 * -0.05) = -0.08 + 0.05 = -0.03
    assert row['spread_theta'] == pytest.approx(-0.03)
    
    # Expected Value check (rough logic check)
    # Current price 152. Bull Call 150/155.
    # At 152, intrinsic value is (152-150)*100 = 200.
    # Cost is 300. Net is -100.
    # But IV is 0.20, 30 days. Stock could go up.
    # We just ensure it's calculated and not NaN
    assert not np.isnan(row['expected_value'])

def test_calc_spreads_empty():
    result = calc_spreads(pd.DataFrame())
    assert result.empty

def test_get_page_spreads_filtering(sample_credit_spread_data):
    # Add a row with negative profit
    bad_row = sample_credit_spread_data.iloc[0:1].copy()
    bad_row['sell_last_option_price'] = 0.5
    bad_row['buy_last_option_price'] = 1.0
    
    data = pd.concat([sample_credit_spread_data, bad_row])
    result = get_page_spreads(data)
    
    # The bad row should be filtered out because max_profit <= 0
    assert len(result) == 1
