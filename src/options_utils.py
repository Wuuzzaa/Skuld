import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional
from config import NUM_SIMULATIONS, RANDOM_SEED, RISK_FREE_RATE, IV_CORRECTION_MODE
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Constants
MULTIPLIER = 100
EARNINGS_WARNING_DAYS = 7
DIVIDEND_YIELD = 0

def calculate_apdi(profit: float, dte: float, bpr: float) -> float:
    """Calculates Annualized Profit per Dollar Invested."""
    if dte <= 0 or bpr <= 0:
        return 0.0
    return (profit / dte / bpr) * 36500

def create_earnings_warning(earnings_date: Any, expiration_date: Any) -> str:
    """Creates an earnings warning string if earnings occur shortly before expiration."""
    earnings_date = pd.to_datetime(earnings_date, errors='coerce')
    expiration_date = pd.to_datetime(expiration_date, errors='coerce')
    
    if pd.notna(earnings_date) and pd.notna(expiration_date) and earnings_date > pd.Timestamp.now():
        days_before_expiration = (expiration_date - earnings_date).days
        if 0 <= days_before_expiration <= EARNINGS_WARNING_DAYS:
            return f'⚠️ {days_before_expiration} days'
    return ''

def format_strike(strike: float) -> str:
    """Formats strike price for URLs."""
    return str(int(strike)) if strike == int(strike) else str(strike)

def format_expiration_date(exp_date: Any) -> str:
    """Formats expiration date for URLs (YYMMDD)."""
    return pd.to_datetime(exp_date).strftime('%y%m%d')

def calculate_expected_value(
    current_price: float,
    dte: float,
    volatility: float,
    options: List[Dict[str, Any]],
    risk_free_rate: float = RISK_FREE_RATE,
    dividend_yield: float = DIVIDEND_YIELD,
    num_simulations: int = NUM_SIMULATIONS,
    random_seed: int = RANDOM_SEED,
    iv_correction: str = IV_CORRECTION_MODE
) -> float:
    """Calculates the Expected Value using Monte Carlo simulation."""
    simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=num_simulations,
        random_seed=random_seed,
        current_price=current_price,
        dte=int(dte),
        volatility=volatility,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        iv_correction=iv_correction
    )
    return simulator.calculate_expected_value(options=options)
