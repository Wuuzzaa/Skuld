

import numpy as np
import pandas as pd
from typing import List, Dict

def simulate_stock_prices(
        current_price: float,
        volatility: float,
        dte: int,
        num_simulations: int = 100000,
        risk_free_rate: float = 0.042,
        dividend_yield: float = 0.015
):
    """
    Simulates stock prices at expiration using lognormal distribution

    Args:
        current_price: Current stock price
        volatility: Annual volatility (e.g. 0.25 for 25%)
        dte: Days to expiration
        risk_free_rate: Risk-free interest rate
        dividend_yield: Dividend yield
        num_simulations: Number of simulated prices

    Returns:
        Array with simulated prices at expiration

    """

    # Drift: For option pricing we use the risk-neutral drift
    drift = risk_free_rate - dividend_yield

    # Generate random normally distributed numbers
    random_shocks = np.random.normal(0, 1, num_simulations)

    # Lognormal distribution: S(T) = S(0) * exp((drift - 0.5*σ²)*T + σ*√T*Z)
    time_to_expiration = dte / 365
    log_returns = (drift - 0.5 * volatility ** 2) * time_to_expiration + volatility * np.sqrt(time_to_expiration) * random_shocks
    simulated_prices = current_price * np.exp(log_returns)

    return simulated_prices


def calculate_option_payoff(
        simulated_prices: np.ndarray,
        strike: float,
        is_call: bool,
        is_long: bool,
        premium: float) -> np.ndarray:
    """
    Calculates option payoffs for all simulated prices

    Args:
        simulated_prices: Array with simulated prices
        strike: Strike price
        is_call: True for call options, False for put options
        is_long: True for long position (bought), False for short position (sold)
        premium: Option premium (always positive value)

    Returns:
        Array with payoffs (profit/loss) for each simulation
    """
    # Intrinsic value at expiration
    if is_call:
        intrinsic_values = np.maximum(simulated_prices - strike, 0)
    else:
        intrinsic_values = np.maximum(strike - simulated_prices, 0)

    # Calculate payoff
    if is_long:
        # Long: Payoff = Intrinsic value - Premium paid
        payoffs = intrinsic_values - premium
    else:
        # Short: Payoff = Premium received - Intrinsic value
        payoffs = premium - intrinsic_values

    return payoffs

def calculate_spread_payoffs(
        simulated_prices: np.ndarray,
        sell_strike: float,
        buy_strike: float,
        is_call: bool,
        sell_premium: float,
        buy_premium: float
):
   payoffs_buy = calculate_option_payoff(
       simulated_prices=simulated_prices,
       strike=buy_strike,
       is_call=is_call,
       is_long=True,
       premium=buy_premium
   )
   payoffs_sell = calculate_option_payoff(
       simulated_prices=simulated_prices,
       strike=sell_strike,
       is_call=is_call,
       is_long=False,
       premium=sell_premium
   )
   payoffs = payoffs_buy + payoffs_sell

   return payoffs


def calculate_spread_expected_value(
        current_price: float,
        volatility: float,
        dte: int,
        short_strike: float,
        short_premium: float,
        short_is_call: bool,
        long_strike: float,
        long_premium: float,
        long_is_call: bool,
        num_simulations: int = 100000,
        random_seed: int = None,
        risk_free_rate: float = 0.042,
        dividend_yield: float = 0.015) -> float:
    """
    Calculates the expected value of an option spread using Monte Carlo simulation

    Args:
        current_price: Current stock price
        volatility: Annual volatility (e.g. 0.25 for 25%)
        dte: Days to expiration
        short_strike: Strike price of the short option
        short_premium: Premium of the short option
        short_is_call: True if short option is a call, False for put
        long_strike: Strike price of the long option
        long_premium: Premium of the long option
        long_is_call: True if long option is a call, False for put
        num_simulations: Number of Monte Carlo simulations
        random_seed: Random seed for reproducible results (None for random)
        risk_free_rate: Risk-free interest rate
        dividend_yield: Dividend yield

    Returns:
        Expected value of the spread (profit/loss per share)
    """

    # Set random seed if provided
    if random_seed is not None:
        np.random.seed(random_seed)

    # Simulate stock prices at expiration
    simulated_prices = simulate_stock_prices(
        current_price=current_price,
        volatility=volatility,
        dte=dte,
        num_simulations=num_simulations,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield
    )

    # Calculate payoffs for short option (sold)
    short_payoffs = calculate_option_payoff(
        simulated_prices=simulated_prices,
        strike=short_strike,
        is_call=short_is_call,
        is_long=False,  # Short position
        premium=short_premium
    )

    # Calculate payoffs for long option (bought)
    long_payoffs = calculate_option_payoff(
        simulated_prices=simulated_prices,
        strike=long_strike,
        is_call=long_is_call,
        is_long=True,  # Long position
        premium=long_premium
    )

    # Total spread payoffs
    spread_payoffs = short_payoffs + long_payoffs

    # Calculate expected value
    expected_value = np.mean(spread_payoffs)

    return expected_value


def calculate_strategy_expected_value(
        current_price: float,
        volatility: float,
        dte: int,
        options: List[Dict[str, float | bool]],
        num_simulations: int = 100000,
        random_seed: int = None,
        risk_free_rate: float = 0.042,
        dividend_yield: float = 0.015) -> float:
    """
    Calculates the expected value of any multi-leg option strategy using Monte Carlo simulation

    Args:
        current_price: Current stock price
        volatility: Annual volatility (e.g. 0.25 for 25%)
        dte: Days to expiration
        options: List of option dictionaries, each containing:
                 - 'strike': Strike price
                 - 'premium': Option premium (always positive)
                 - 'is_call': True for call, False for put
                 - 'is_long': True for long position, False for short position
        num_simulations: Number of Monte Carlo simulations
        random_seed: Random seed for reproducible results (None for random)
        risk_free_rate: Risk-free interest rate
        dividend_yield: Dividend yield

    Returns:
        Expected value of the strategy (profit/loss per share)
    """

    # Set random seed if provided
    if random_seed is not None:
        np.random.seed(random_seed)

    # Simulate stock prices at expiration
    simulated_prices = simulate_stock_prices(
        current_price=current_price,
        volatility=volatility,
        dte=dte,
        num_simulations=num_simulations,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield
    )

    # Initialize total payoffs array
    total_payoffs = np.zeros(num_simulations)

    # Calculate payoffs for each option leg
    for option in options:
        leg_payoffs = calculate_option_payoff(
            simulated_prices=simulated_prices,
            strike=option['strike'],
            is_call=option['is_call'],
            is_long=option['is_long'],
            premium=option['premium']
        )

        # Add to total strategy payoffs
        total_payoffs += leg_payoffs

    # Calculate expected value
    expected_value = np.mean(total_payoffs)

    return expected_value


if __name__ == "__main__":
    expected_value = calculate_spread_expected_value(
        current_price=150,
        volatility=0.25,
        dte=35,
        short_strike=155,
        short_premium=10,
        short_is_call=True,
        long_strike=160,
        long_premium=5,
        long_is_call=True,
        num_simulations=100000,
        random_seed=42,
        risk_free_rate=0.042,
        dividend_yield=0.015
    )

    # Definition der Options-Legs
    options = [
        {
            'strike': 155,
            'premium': 10,
            'is_call': True,
            'is_long': False},  # Short Call
        {
            'strike': 160,
            'premium': 5,
            'is_call': True,
            'is_long': True}  # Long Call
    ]

    # Aufruf der neuen Funktion
    strategy_expected_value = calculate_strategy_expected_value(
        current_price=150,
        volatility=0.25,
        dte=35,
        options=options,
        num_simulations=100000,
        random_seed=42,
        risk_free_rate=0.042,
        dividend_yield=0.015
    )

    pass
