import pytest
import numpy as np
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

def test_managed_simulator():
    # Setup simulator
    simulator = UniversalOptionsMonteCarloSimulator(
        current_price=100.0,
        volatility=0.2,
        dte=45,
        num_simulations=1000,
        random_seed=42
    )
    
    # 1. Test standard short put payoff (no management)
    options_no_mgm = [{
        'strike': 95,
        'premium': 2.0,
        'is_call': False,
        'is_long': False
    }]
    
    final_prices, payoffs, cashflow = simulator._calculate_strategy_payoffs(options_no_mgm)
    ev_no_mgm = np.mean(payoffs)
    
    # 2. Test managed short put payoff (TP 50%)
    options_mgm = [{
        'strike': 95,
        'premium': 2.0,
        'is_call': False,
        'is_long': False,
        'take_profit_pct': 50 # Close at 1.0 premium (50% profit)
    }]
    
    final_prices_m, payoffs_m, cashflow_m = simulator._calculate_managed_strategy_payoffs(options_mgm)
    ev_mgm = np.mean(payoffs_m)
    
    print(f"EV No MGM: {ev_no_mgm}")
    print(f"EV MGM (TP 50%): {ev_mgm}")
    
    # Management should generally change EV (often increase Win Rate but decrease total profit per trade)
    assert ev_no_mgm != ev_mgm
    
    # 3. Test Greeks
    greeks = simulator.calculate_greeks(options_no_mgm)
    assert 'delta' in greeks
    assert 'gamma' in greeks
    assert 'vega' in greeks
    # Short put should have positive delta
    assert greeks['delta'] > 0

if __name__ == "__main__":
    test_managed_simulator()
