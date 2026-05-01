import pandas as pd
import numpy as np
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass
from config import NUM_SIMULATIONS, RANDOM_SEED, RISK_FREE_RATE, IV_CORRECTION_MODE
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Constants
MULTIPLIER = 100
EARNINGS_WARNING_DAYS = 7
DIVIDEND_YIELD = 0

# Setup logging
logger = logging.getLogger(os.path.basename(__file__))

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
    # Management parameters
    take_profit_pct: Optional[float] = None  # e.g., 50 for 50%
    stop_loss_pct: Optional[float] = None    # e.g., 200 for 200%
    dte_close: Optional[int] = None          # e.g., 21 for 21 DTE
    planned_dte: Optional[int] = None       # Custom DTE for this leg

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
    expected_value_managed: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0

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
    num_simulations: int = 5000,
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
    num_simulations: int = 5000,
    random_seed: int = RANDOM_SEED,
    iv_correction: str = IV_CORRECTION_MODE
) -> StrategyMetrics:
    """Calculates all metrics for a given strategy with arbitrary legs."""
    
    # 1. Expected Value & IV Correction
    options_sim = [
        {
            'strike': leg.strike, 
            'premium': leg.premium, 
            'is_call': leg.is_call, 
            'is_long': leg.is_long,
            'take_profit_pct': leg.take_profit_pct,
            'stop_loss_pct': leg.stop_loss_pct,
            'dte_close': leg.dte_close,
            'planned_dte': leg.planned_dte
        }
        for leg in legs
    ]

    # Check if any management parameters are present
    has_management = any(
        opt.get('take_profit_pct') is not None or 
        opt.get('stop_loss_pct') is not None or 
        opt.get('dte_close') is not None or
        (opt.get('planned_dte') is not None and opt.get('planned_dte') < dte)
        for opt in options_sim
    )
    
    # 1. Initialize Simulator and Calculate Expected Value & IV Correction
    simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=num_simulations,
        current_price=current_price,
        dte=int(dte),
        volatility=volatility,
        risk_free_rate=risk_free_rate,
        dividend_yield=dividend_yield,
        random_seed=random_seed,
        iv_correction=iv_correction
    )

    ev_managed = simulator.calculate_expected_value(options=options_sim)
    
    # Also calculate static EV for comparison if management is active
    if has_management:
        options_static = [opt.copy() for opt in options_sim]
        for opt in options_static:
            opt['take_profit_pct'] = None
            opt['stop_loss_pct'] = None
            opt['dte_close'] = None
            opt['planned_dte'] = None
            
        ev_static = simulator.calculate_expected_value(options=options_static)
    else:
        ev_static = ev_managed

    # Ensure we use floats to avoid any 0-display issues if they were objects
    ev_static = float(ev_static)
    ev_managed = float(ev_managed)
    
    # Extra check to log if they are suspiciously 0
    if ev_managed == 0.0:
        logger.warning(f"Calculated EV Managed is 0.0 for strategy with current_price={current_price}")

    # Calculate Greeks using the same simulator
    greeks = simulator.calculate_greeks(options_sim)
    
    # 2. Max Profit, Max Loss, BPR
    # For arbitrary legs, we use a range of stock prices to find max profit/loss (analytical)
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
    apdi_ev = calculate_apdi(ev_managed, dte, bpr)

    return StrategyMetrics(
        max_profit=max_profit,
        max_loss=max_loss,
        bpr=bpr,
        expected_value=ev_static,
        expected_value_managed=ev_managed,
        total_theta=total_theta,
        profit_to_bpr=profit_to_bpr,
        apdi=apdi,
        apdi_ev=apdi_ev,
        iv_correction_factor=simulator.iv_correction_factor,
        corrected_volatility=simulator.volatility,
        delta=greeks.get('delta', 0.0),
        gamma=greeks.get('gamma', 0.0),
        vega=greeks.get('vega', 0.0)
    )
