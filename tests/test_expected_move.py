import pytest
from math import sqrt
from src.spreads_calculation import calculate_expected_move


def test_calculate_expected_move_basic():
    """Test basic expected move calculation with known values."""
    # Test case: $100 stock, 30 days to expiration, 25% IV
    underlying_price = 100.0
    days_to_expiration = 30
    implied_volatility = 0.25
    
    result = calculate_expected_move(underlying_price, days_to_expiration, implied_volatility)
    
    # Expected calculation:
    # time_fraction = sqrt(30 / 365) = sqrt(0.08219) = 0.2867
    # expected_move_dollar = 0.25 * 100.0 * 0.2867 = 7.17
    # expected_move_percent = (7.17 / 100.0) * 100 = 7.17%
    
    expected_dollar = round(0.25 * 100.0 * sqrt(30 / 365), 2)
    expected_percent = round((expected_dollar / 100.0) * 100, 2)
    
    assert result['dollar'] == expected_dollar
    assert result['percent'] == expected_percent
    assert isinstance(result['dollar'], float)
    assert isinstance(result['percent'], float)


def test_calculate_expected_move_edge_cases():
    """Test edge cases for expected move calculation."""
    
    # Test zero values
    result = calculate_expected_move(0, 30, 0.25)
    assert result['dollar'] == 0.0
    assert result['percent'] == 0.0
    
    result = calculate_expected_move(100, 0, 0.25)
    assert result['dollar'] == 0.0
    assert result['percent'] == 0.0
    
    result = calculate_expected_move(100, 30, 0)
    assert result['dollar'] == 0.0
    assert result['percent'] == 0.0
    
    # Test negative values
    result = calculate_expected_move(-100, 30, 0.25)
    assert result['dollar'] == 0.0
    assert result['percent'] == 0.0


def test_calculate_expected_move_real_scenarios():
    """Test expected move calculation with realistic market scenarios."""
    
    # High IV scenario (e.g., earnings week)
    result = calculate_expected_move(150.0, 7, 0.60)  # 60% IV, 1 week
    assert result['dollar'] > 0
    assert result['percent'] > 0
    
    # Low IV scenario (e.g., stable large cap)
    result = calculate_expected_move(50.0, 45, 0.15)  # 15% IV, 45 days
    assert result['dollar'] > 0
    assert result['percent'] > 0
    
    # For the same stock and time, higher IV should give higher expected move
    high_iv = calculate_expected_move(100.0, 30, 0.40)
    low_iv = calculate_expected_move(100.0, 30, 0.20)
    
    assert high_iv['dollar'] > low_iv['dollar']
    assert high_iv['percent'] > low_iv['percent']
    
    # For the same stock and IV, longer time should give higher expected move
    long_time = calculate_expected_move(100.0, 60, 0.25)
    short_time = calculate_expected_move(100.0, 15, 0.25)
    
    assert long_time['dollar'] > short_time['dollar']
    assert long_time['percent'] > short_time['percent']


def test_calculate_expected_move_precision():
    """Test that expected move calculation returns proper precision."""
    result = calculate_expected_move(123.456, 37, 0.2789)
    
    # Check that dollar amount is rounded to 2 decimal places
    assert len(str(result['dollar']).split('.')[-1]) <= 2
    
    # Check that percentage is rounded to 2 decimal places
    assert len(str(result['percent']).split('.')[-1]) <= 2


def test_calculate_expected_move_consistency():
    """Test that expected move calculation is consistent with POP calculation."""
    # The expected move should match the std_dev calculation in calculate_pop
    underlying_price = 100.0
    days_to_expiration = 30
    implied_volatility = 0.25
    
    result = calculate_expected_move(underlying_price, days_to_expiration, implied_volatility)
    
    # Manual calculation of std_dev from calculate_pop logic
    time_fraction = sqrt(days_to_expiration / 365)
    std_dev = implied_volatility * underlying_price * time_fraction
    
    assert result['dollar'] == round(std_dev, 2)