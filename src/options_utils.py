import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from config import NUM_SIMULATIONS, RANDOM_SEED, RISK_FREE_RATE, IV_CORRECTION_MODE
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Constants
MULTIPLIER = 100
EARNINGS_WARNING_DAYS = 7
DIVIDEND_YIELD = 0

@dataclass
class OptionLeg:
    strike: float
    premium: float
    is_call: bool
    is_long: bool
    symbol: Optional[str] = None
    delta: Optional[float] = None
    iv: Optional[float] = None
    theta: Optional[float] = None
    oi: Optional[int] = None
    volume: Optional[int] = None
    expected_move: Optional[float] = None

@dataclass
class StrategyMetrics:
    max_profit: float
    max_loss: float
    bpr: float
    expected_value: float
    total_theta: float
    profit_to_bpr: float
    apdi: float
    apdi_ev: float
    iv_correction_factor: float
    corrected_volatility: float

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
    iv_correction: str = IV_CORRECTION_MODE,
    return_details: bool = False
) -> float | Dict[str, Any]:
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
    ev = simulator.calculate_expected_value(options=options)
    
    if return_details:
        return {
            "expected_value": ev,
            "iv_correction_factor": simulator.iv_correction_factor,
            "corrected_volatility": simulator.volatility
        }
    return ev

def calculate_strategy_metrics(
    current_price: float,
    dte: float,
    volatility: float,
    legs: List[OptionLeg],
    risk_free_rate: float = RISK_FREE_RATE,
    dividend_yield: float = DIVIDEND_YIELD,
    num_simulations: int = NUM_SIMULATIONS,
    random_seed: int = RANDOM_SEED,
    iv_correction: str = IV_CORRECTION_MODE
) -> StrategyMetrics:
    """Calculates all metrics for a given strategy with arbitrary legs."""
    
    # 1. Expected Value & IV Correction
    options_sim = [
        {'strike': leg.strike, 'premium': leg.premium, 'is_call': leg.is_call, 'is_long': leg.is_long}
        for leg in legs
    ]
    
    ev_details = calculate_expected_value(
        current_price=current_price,
        dte=dte,
        volatility=volatility,
        options=options_sim,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        num_simulations=num_simulations,
        random_seed=random_seed,
        iv_correction=iv_correction,
        return_details=True
    )
    
    # 2. Max Profit, Max Loss, BPR
    # To calculate Max Profit/Loss/BPR we use a simulation approach or analytical if possible.
    # For arbitrary legs, we can use the simulator's payoff analysis.
    simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=1000, # Fewer for metrics is okay if we just want min/max
        current_price=current_price,
        dte=int(dte),
        volatility=volatility,
        iv_correction='none' # No correction for static metrics
    )
    
    # We need a range of stock prices to find max profit/loss
    # Use a wide range around current price and strikes
    strikes = [leg.strike for leg in legs]
    min_strike = min(strikes) if strikes else current_price
    max_strike = max(strikes) if strikes else current_price
    price_range = np.linspace(min_strike * 0.5, max_strike * 1.5, 1000)
    
    payoffs = np.zeros_like(price_range)
    net_premium = 0
    for leg in legs:
        # Premium: negative if bought, positive if sold
        mult = 1 if not leg.is_long else -1
        net_premium += mult * leg.premium
        
        # Payoff at expiration
        if leg.is_call:
            leg_payoff = np.maximum(0, price_range - leg.strike)
        else:
            leg_payoff = np.maximum(0, leg.strike - price_range)
            
        payoffs += (1 if leg.is_long else -1) * leg_payoff

    total_profit_at_exp = (payoffs + net_premium) * MULTIPLIER
    max_profit = np.max(total_profit_at_exp)
    max_loss = -np.min(total_profit_at_exp)
    
    # BPR logic: for credit strategies it's usually the max loss
    # For complex ones it might be margin, but here we use max_loss as proxy
    bpr = max(0.0, max_loss)

    # 3. Total Theta
    # Theta is usually negative for single options.
    # We sum up the individual thetas as they are.
    # Long positions: +theta (e.g., -0.05), Short positions: -theta (e.g., -(-0.05) = +0.05)
    total_theta = sum((leg.theta if leg.theta is not None else 0) * (1 if leg.is_long else -1) for leg in legs)

    # 4. Ratios
    profit_to_bpr = max_profit / bpr if bpr > 0 else 0
    apdi = calculate_apdi(max_profit, dte, bpr)
    apdi_ev = calculate_apdi(ev_details['expected_value'], dte, bpr)

    return StrategyMetrics(
        max_profit=max_profit,
        max_loss=max_loss,
        bpr=bpr,
        expected_value=ev_details['expected_value'],
        total_theta=total_theta,
        profit_to_bpr=profit_to_bpr,
        apdi=apdi,
        apdi_ev=apdi_ev,
        iv_correction_factor=ev_details['iv_correction_factor'],
        corrected_volatility=ev_details['corrected_volatility']
    )
