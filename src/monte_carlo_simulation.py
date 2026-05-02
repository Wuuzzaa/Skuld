import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Union, Optional
from scipy.stats import norm
import functools
import logging
from src.decorator_log_function import log_function

from config import TRANSACTION_COST_PER_CONTRACT, RANDOM_SEED, NUM_SIMULATIONS, RISK_FREE_RATE, IV_CORRECTION_MODE


class UniversalOptionsMonteCarloSimulator:
    """
    Universal Monte-Carlo simulation for arbitrary multi-leg options strategies

    The logic is simple:
    1. Each option has only its intrinsic value at expiration
    2. Long positions: Pay premium today, receive intrinsic value at expiration
    3. Short positions: Receive premium today, pay intrinsic value at expiration
    4. Expected value = Average of all possible payoffs (discounted)
    5. Transaction costs are applied per contract (covering 100 shares each)
    6. Each entry in options list = exactly 1 contract
    7. IV correction adjusts for systematic implied volatility overestimation
    """

    def __init__(self,
                 current_price: float,
                 volatility: float,
                 dte: int,
                 risk_free_rate: float = RISK_FREE_RATE,
                 dividend_yield: float = 0.00,
                 num_simulations: int = NUM_SIMULATIONS,
                 random_seed: int = RANDOM_SEED,
                 transaction_cost_per_contract: float = TRANSACTION_COST_PER_CONTRACT,
                 iv_correction: Union[str, float] = IV_CORRECTION_MODE):
        """
        Initialize the universal Monte-Carlo simulator

        Args:
            current_price: Current stock price
            volatility: Implied volatility from market (e.g., 0.35 for 35%)
            dte: Days to expiration
            risk_free_rate: Risk-free interest rate
            dividend_yield: Dividend yield
            num_simulations: Number of Monte-Carlo simulations
            random_seed: Seed for reproducible results
            transaction_cost_per_contract: Transaction cost per options contract (covers 100 shares)
            iv_correction: IV correction mode:
                          - "auto": Automatic correction based on DTE and research
                          - float (0.0-1.0): Manual percentage reduction (e.g., 0.15 for 15% reduction)
                          - 0.0: No correction (use market IV as-is)
        """
        self.current_price = current_price
        self.raw_volatility = volatility  # Store original market IV
        self.dte = dte
        self.risk_free_rate = risk_free_rate
        self.dividend_yield = dividend_yield
        self.num_simulations = num_simulations
        self.random_seed = random_seed
        self.transaction_cost_per_contract = transaction_cost_per_contract
        self.iv_correction = iv_correction
        self.time_to_expiration = dte / 365

        # Apply IV correction
        self.volatility = self._apply_iv_correction(volatility, dte, iv_correction)

        # Store correction factor for reporting
        if isinstance(iv_correction, str) and iv_correction == "auto":
            self.iv_correction_factor = self._calculate_iv_correction_factor(dte)
        elif isinstance(iv_correction, str) and iv_correction.lower() == "none":
            self.iv_correction_factor = 0.0
        elif isinstance(iv_correction, (int, float)) and iv_correction > 0:
            self.iv_correction_factor = float(iv_correction)
        else:
            self.iv_correction_factor = 0.0

        # Set random seed
        if random_seed is not None:
            np.random.seed(random_seed)

        self.expected_value = None # calculated not on init

    def __str__(self):
        attrs = vars(self)
        return "\n".join(f"{key}: {value}" for key, value in attrs.items())


    def _calculate_iv_correction_factor(self, dte: int) -> float:
        """
        Calculate IV correction factor based on DTE and volatility risk premium research

        Based on academic research showing systematic IV overestimation:
        - VIX term structure typically in contango (longer terms overpriced)
        - Volatility risk premium: investors pay "fear premium"
        - Time decay effects more pronounced at shorter DTE

        Sources:
        - VIX term structure research showing contango bias
        - Volatility risk premium studies indicating 10-20% overestimation

        Formula: correction = base_bias + (dte_bias * log(dte/30))
        """
        if dte <= 0:
            return 0.0

        # Base overestimation: ~8% minimum bias (even at 30 DTE)
        # This reflects the fundamental volatility risk premium
        base_bias = 0.08

        # Additional bias for longer terms (contango effect)
        # Log scaling reflects diminishing returns of term structure effect
        # Peaks around 90-120 DTE, then plateaus
        dte_bias = 0.05 * np.log(max(dte, 1) / 30.0)

        # Combined correction factor
        total_correction = base_bias + dte_bias

        # Realistic bounds: base_bias minimum, 25% maximum
        return max(base_bias, min(0.25, total_correction))

    def _apply_iv_correction(self, market_iv: float, dte: int, correction_mode: Union[str, float]) -> float:
        """
        Apply IV correction based on the specified mode

        Args:
            market_iv: Original implied volatility from market
            dte: Days to expiration
            correction_mode: Correction mode specification

        Returns:
            Corrected implied volatility
        """
        if isinstance(correction_mode, str) and correction_mode.lower() == "auto":
            # Automatic correction based on research
            correction_factor = self._calculate_iv_correction_factor(dte)
            corrected_iv = market_iv * (1.0 - correction_factor)
        elif isinstance(correction_mode, str) and correction_mode.lower() == "none":
            # No correction
            corrected_iv = market_iv
        elif isinstance(correction_mode, (int, float)):
            if correction_mode == 0.0:
                # No correction
                corrected_iv = market_iv
            elif 0.0 < correction_mode <= 1.0:
                # Manual percentage reduction
                corrected_iv = market_iv * (1.0 - correction_mode)
            else:
                raise ValueError(f"IV correction must be between 0.0 and 1.0, got {correction_mode}")
        else:
            raise ValueError(f"IV correction must be 'auto' or float between 0.0-1.0, got {correction_mode}")

        # Ensure corrected IV is positive and reasonable
        return max(0.01, corrected_iv)  # Minimum 1% IV

    @staticmethod
    @functools.lru_cache(maxsize=128)
    def _generate_price_paths_cached(current_price: float, volatility: float, dte: int,
                                    risk_free_rate: float, dividend_yield: float,
                                    num_simulations: int, random_seed: int) -> np.ndarray:
        """
        Internal cached method for generating price paths.
        Parameters must be hashable.
        """
        # For Monte-Carlo option valuation: Risk-neutral drift
        drift = risk_free_rate - dividend_yield

        # Reset random seed for consistent results
        if random_seed is not None:
            np.random.seed(random_seed)

        # Time steps: daily
        dt = 1 / 365
        num_steps = dte

        # Generate all random shocks at once
        random_shocks = np.random.standard_normal((num_simulations, num_steps))
        
        # Calculate daily log returns
        log_returns = ((drift - 0.5 * volatility ** 2) * dt +
                       volatility * np.sqrt(dt) * random_shocks)
        
        # Cumulative sum of log returns to get price paths
        cumulative_log_returns = np.cumsum(log_returns, axis=1)
        
        # Prepend zeros for the starting price (at t=0)
        starting_log_returns = np.zeros((num_simulations, 1))
        all_log_returns = np.hstack([starting_log_returns, cumulative_log_returns])
        
        # Calculate price paths
        price_paths = current_price * np.exp(all_log_returns)
        
        return price_paths

    def simulate_stock_price_paths(self) -> np.ndarray:
        """
        Simulate stock price paths using geometric Brownian motion.
        Uses a static cached method to reuse paths if parameters are identical.

        Returns:
            np.ndarray: Matrix of simulated stock prices (num_simulations, dte + 1)
        """
        # We must ensure all parameters are of types that can be hashed by lru_cache
        # float, int are fine.
        return self._generate_price_paths_cached(
            float(self.current_price),
            float(self.volatility),
            int(self.dte),
            float(self.risk_free_rate),
            float(self.dividend_yield),
            int(self.num_simulations),
            int(self.random_seed) if self.random_seed is not None else None
        )

    def simulate_stock_prices(self) -> np.ndarray:
        """
        Simulate stock prices at expiration using geometric Brownian motion

        Uses risk-neutral valuation for options pricing models with corrected IV
        """
        # Legacy support: return only the final prices
        price_paths = self.simulate_stock_price_paths()
        return price_paths[:, -1]

    def calculate_option_intrinsic_value(self,
                                         stock_price: float,
                                         strike: float,
                                         is_call: bool) -> float:
        """
        Calculate intrinsic value of an option at expiration

        Args:
            stock_price: Stock price at expiration
            strike: Strike price of the option
            is_call: True for Call, False for Put

        Returns:
            Intrinsic value of the option
        """
        if is_call:
            return max(stock_price - strike, 0)
        else:
            return max(strike - stock_price, 0)

    def calculate_single_option_payoff(self,
                                       simulated_prices: np.ndarray,
                                       strike: float,
                                       premium: float,
                                       is_call: bool,
                                       is_long: bool) -> np.ndarray:
        """
        Calculate payoff for a single option contract across all simulations

        Args:
            simulated_prices: Array of simulated stock prices at expiration
            strike: Strike price of the option
            premium: Premium paid/received per share (always positive)
            is_call: True for Call option, False for Put option
            is_long: True for Long position (bought), False for Short position (sold)

        Returns:
            Array of payoffs for each simulation for ONE contract (includes transaction costs)
        """
        # Intrinsic values at expiration for all simulations (per share)
        if is_call:
            intrinsic_values_per_share = np.maximum(simulated_prices - strike, 0)
        else:
            intrinsic_values_per_share = np.maximum(strike - simulated_prices, 0)

        # Convert to per-contract values (100 shares per contract)
        intrinsic_values_per_contract = intrinsic_values_per_share * 100
        premium_per_contract = premium * 100

        # Payoff calculation depending on position (for 1 contract)
        if is_long:
            # Long: Pay premium today, receive intrinsic value at expiration, pay transaction costs
            payoffs_per_contract = (intrinsic_values_per_contract -
                                    premium_per_contract -
                                    self.transaction_cost_per_contract)
        else:
            # Short: Receive premium today, pay intrinsic value at expiration, pay transaction costs
            payoffs_per_contract = (premium_per_contract -
                                    intrinsic_values_per_contract -
                                    self.transaction_cost_per_contract)

        return payoffs_per_contract

    def _black_scholes_vectorized(self, S, K, T, r, sigma, is_call):
        """
        Internal vectorized Black-Scholes price calculation
        Highly optimized for performance.
        """
        # Handle expiration (T=0)
        T_safe = np.where(T > 0, T, 1e-9)
        
        sqrt_T = np.sqrt(T_safe)
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T_safe) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T

        # Fast approximation of norm.cdf for performance (Abramowitz & Stegun)
        # significantly faster than scipy.stats.norm.cdf
        def fast_norm_cdf(x):
            abs_x = np.abs(x)
            t = 1.0 / (1.0 + 0.2316419 * abs_x)
            a1 = 0.319381530
            a2 = -0.356563782
            a3 = 1.781477937
            a4 = -1.821255978
            a5 = 1.330274429
            
            p = 0.3989422804014327  # 1/sqrt(2*pi)
            
            prob = 1.0 - p * np.exp(-0.5 * x * x) * (
                a1 * t + a2 * t**2 + a3 * t**3 + a4 * t**4 + a5 * t**5
            )
            return np.where(x >= 0, prob, 1.0 - prob)

        nd1 = fast_norm_cdf(d1)
        nd2 = fast_norm_cdf(d2)
        exp_rt = np.exp(-r * T_safe)

        # Call price: S * N(d1) - K * e^(-rT) * N(d2)
        call_prices = S * nd1 - K * exp_rt * nd2
        
        # Put price: K * e^(-rT) * N(-d2) - S * N(-d1)
        put_prices = K * exp_rt * (1 - nd2) - S * (1 - nd1)

        prices = np.where(is_call, call_prices, put_prices)
        
        # At expiration (T=0), use intrinsic value
        if np.any(T <= 0):
            intrinsic_call = np.maximum(S - K, 0)
            intrinsic_put = np.maximum(K - S, 0)
            intrinsic = np.where(is_call, intrinsic_call, intrinsic_put)
            prices = np.where(T > 0, prices, intrinsic)

        return prices

    def _calculate_strategy_payoffs(self, options: List[Dict]) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Helper method to calculate strategy payoffs and initial cashflow

        Args:
            options: List of option dictionaries

        Returns:
            Tuple of (simulated_prices, total_payoffs, initial_cashflow)
        """
        # Simulate stock prices at expiration
        simulated_prices = self.simulate_stock_prices()

        # Initialize total payoffs
        total_payoffs = np.zeros(self.num_simulations)

        # Calculate net cashflow at inception
        initial_cashflow = 0

        for option in options:
            # Analyze single leg (always 1 contract)
            leg_payoffs = self.calculate_single_option_payoff(
                simulated_prices=simulated_prices,
                strike=option['strike'],
                premium=option['premium'],
                is_call=option['is_call'],
                is_long=option['is_long']
            )

            # Add to total payoff
            total_payoffs += leg_payoffs

            # Cashflow tracking (for 1 contract)
            premium_per_contract = option['premium'] * 100
            transaction_cost_per_contract = self.transaction_cost_per_contract

            if option['is_long']:
                # Long: Pay premium + transaction costs
                initial_cashflow -= (premium_per_contract + transaction_cost_per_contract)
            else:
                # Short: Receive premium - transaction costs
                initial_cashflow += (premium_per_contract - transaction_cost_per_contract)

        return simulated_prices, total_payoffs, initial_cashflow

    def _calculate_managed_strategy_payoffs(self, options: List[Dict]) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Calculate strategy payoffs considering SL/TP and early exit logic
        Optimized version with vectorized management logic.
        """
        # 1. Simulate price paths (simulations, steps)
        price_paths = self.simulate_stock_price_paths()
        num_steps = price_paths.shape[1]
        
        # 2. Extract option parameters
        num_legs = len(options)
        strikes = np.array([opt.get('strike') for opt in options])
        premiums = np.array([opt.get('premium') for opt in options])
        is_calls = np.array([opt.get('is_call', True) for opt in options])
        is_longs = np.array([opt.get('is_long', True) for opt in options])
        
        tp_pcts = np.array([opt.get('take_profit_pct') if opt.get('take_profit_pct') is not None else np.nan for opt in options])
        sl_pcts = np.array([opt.get('stop_loss_pct') if opt.get('stop_loss_pct') is not None else np.nan for opt in options])
        dte_closes = np.array([opt.get('dte_close') if opt.get('dte_close') is not None else -1 for opt in options])
        planned_dtes = np.array([opt.get('planned_dte') if opt.get('planned_dte') is not None else self.dte for opt in options])
        
        # 3. Initialize exit tracking
        # closed_at_step: (num_simulations, num_legs)
        closed_at_step = np.zeros((self.num_simulations, num_legs), dtype=int)
        exit_prices = np.zeros((self.num_simulations, num_legs))
        
        # Track WHY it was closed (for each leg)
        # 0: Expiration, 1: TP, 2: SL, 3: DTE Close, 4: Planned DTE
        exit_reasons = np.zeros((self.num_simulations, num_legs), dtype=int)
        
        # Days remaining for each step
        days_remaining = np.arange(self.dte, -1, -1)
        t_years = days_remaining / 365.0
        
        # Step size optimization
        step_size = 1
        if self.dte > 30:
            step_size = max(1, self.dte // 30)

        # Prepare masks for legs with specific management
        has_tp = ~np.isnan(tp_pcts)
        has_sl = ~np.isnan(sl_pcts)
        has_dc = dte_closes != -1
        
        # Pre-calculate trigger thresholds
        tp_thresholds = np.zeros(num_legs)
        sl_thresholds = np.zeros(num_legs)
        
        for l in range(num_legs):
            if has_tp[l]:
                tp_decimal = tp_pcts[l] / 100.0
                tp_thresholds[l] = premiums[l] * (1 + tp_decimal) if is_longs[l] else premiums[l] * (1 - tp_decimal)
            if has_sl[l]:
                sl_decimal = sl_pcts[l] / 100.0
                sl_thresholds[l] = premiums[l] * (1 - sl_decimal) if is_longs[l] else premiums[l] * (1 + sl_decimal)

        # 4. Iterate through days
        for step in range(step_size, num_steps, step_size):
            if step + step_size >= num_steps:
                step = num_steps - 1
            
            current_dte = days_remaining[step]
            
            # Check which legs are still active in which simulations
            active_mask = (closed_at_step == 0)
            if not np.any(active_mask):
                break
                
            s_current = price_paths[:, step].reshape(-1, 1) # (sims, 1)
            
            # Only calculate BS for legs that are active in at least one simulation
            active_legs = np.any(active_mask, axis=0)
            if not np.any(active_legs):
                break

            # Calculate prices for ALL legs (vectorized over simulations)
            # Optimization: could sub-select active_legs here to reduce BS calls if many legs
            leg_prices = self._black_scholes_vectorized(
                s_current, 
                strikes.reshape(1, -1), 
                t_years[step], 
                self.risk_free_rate, 
                self.volatility, 
                is_calls.reshape(1, -1)
            )
            
            # Vectorized trigger evaluation
            triggered = np.zeros((self.num_simulations, num_legs), dtype=bool)
            
            # TP trigger
            if np.any(has_tp):
                long_tp = (leg_prices >= tp_thresholds) & is_longs & has_tp
                short_tp = (leg_prices <= tp_thresholds) & (~is_longs) & has_tp
                tp_triggered = (long_tp | short_tp) & active_mask
                
                closed_at_step[tp_triggered] = step
                exit_prices[tp_triggered] = leg_prices[tp_triggered]
                exit_reasons[tp_triggered] = 1
                active_mask = (closed_at_step == 0)
                
            # SL trigger
            if np.any(has_sl):
                long_sl = (leg_prices <= sl_thresholds) & is_longs & has_sl
                short_sl = (leg_prices >= sl_thresholds) & (~is_longs) & has_sl
                sl_triggered = (long_sl | short_sl) & active_mask
                
                closed_at_step[sl_triggered] = step
                exit_prices[sl_triggered] = leg_prices[sl_triggered]
                exit_reasons[sl_triggered] = 2
                active_mask = (closed_at_step == 0)
                
            # DTE Close trigger
            if np.any(has_dc):
                dc_triggered = (current_dte <= dte_closes) & has_dc & active_mask
                
                closed_at_step[dc_triggered] = step
                exit_prices[dc_triggered] = leg_prices[dc_triggered]
                exit_reasons[dc_triggered] = 3
                active_mask = (closed_at_step == 0)
            
            # Planned DTE trigger
            pdte_triggered = (step >= (self.dte - planned_dtes)) & active_mask
            
            closed_at_step[pdte_triggered] = step
            exit_prices[pdte_triggered] = leg_prices[pdte_triggered]
            exit_reasons[pdte_triggered] = 4
            active_mask = (closed_at_step == 0)
            
            # Expiration
            if step == num_steps - 1:
                exp_triggered = active_mask
                closed_at_step[exp_triggered] = step
                exit_prices[exp_triggered] = leg_prices[exp_triggered]
                exit_reasons[exp_triggered] = 0
                active_mask = (closed_at_step == 0)

        # 5. Calculate payoffs
        initial_cashflow = np.sum(np.where(is_longs, -premiums, premiums)) * 100
        
        # Store exit statistics in the object for later retrieval if needed
        self._last_exit_reasons = exit_reasons

        # Leg profits: (Exit - Entry) for Long, (Entry - Exit) for Short
        # exit_prices shape (sims, legs)
        # premiums shape (legs,)
        if num_legs > 0:
            leg_profits = np.where(is_longs, 
                                   (exit_prices - premiums) * 100, 
                                   (premiums - exit_prices) * 100)
            # Subtract transaction costs for each leg
            leg_profits -= self.transaction_cost_per_contract
            total_payoffs = np.sum(leg_profits, axis=1)
        else:
            total_payoffs = np.zeros(self.num_simulations)

        return price_paths[:, -1], total_payoffs, initial_cashflow

    @log_function
    def calculate_expected_value(self, options: List[Dict]) -> float:
        """
        Calculate only the expected value of the strategy (fast computation)

        Args:
            options: List of option dictionaries

        Returns:
            Expected value of the strategy (discounted to present value)
        """
        # Check if any management parameters are present
        has_management = any(
            opt.get('take_profit_pct') is not None or 
            opt.get('stop_loss_pct') is not None or 
            opt.get('dte_close') is not None or
            (opt.get('planned_dte') is not None and opt.get('planned_dte') < self.dte)
            for opt in options
        )

        if has_management:
            _, total_payoffs, _ = self._calculate_managed_strategy_payoffs(options)
        else:
            _, total_payoffs, _ = self._calculate_strategy_payoffs(options)

        # Calculate expected value
        expected_value_raw = np.mean(total_payoffs)

        # Discount to present value
        discount_factor = np.exp(-self.risk_free_rate * self.time_to_expiration)
        self.expected_value = expected_value_raw * discount_factor

        return self.expected_value

    def calculate_expected_value_batch(self, strategies: List[List[Dict]]) -> List[float]:
        """
        Calculate expected values for multiple strategies sharing the same underlying parameters.
        Highly optimized for screening large numbers of strategies.
        """
        # Check if any strategy needs management
        any_management = False
        for options in strategies:
            if any(
                opt.get('take_profit_pct') is not None or 
                opt.get('stop_loss_pct') is not None or 
                opt.get('dte_close') is not None or
                (opt.get('planned_dte') is not None and opt.get('planned_dte') < self.dte)
                for opt in options
            ):
                any_management = True
                break
        
        # 1. Simulate price paths once (or reuse from cache)
        if any_management:
            # Need full paths for management
            price_paths = self.simulate_stock_price_paths()
            simulated_prices_at_exp = price_paths[:, -1]
        else:
            # Only need expiration prices
            simulated_prices_at_exp = self.simulate_stock_prices()
            price_paths = None
        
        results = []
        discount_factor = np.exp(-self.risk_free_rate * self.time_to_expiration)
        
        for options in strategies:
            # Check for management
            has_management = any(
                opt.get('take_profit_pct') is not None or 
                opt.get('stop_loss_pct') is not None or 
                opt.get('dte_close') is not None or
                (opt.get('planned_dte') is not None and opt.get('planned_dte') < self.dte)
                for opt in options
            )
            
            if has_management:
                # Still use managed logic (already vectorized within one strategy)
                # Note: self.simulate_stock_price_paths() will return the cached paths
                _, total_payoffs, _ = self._calculate_managed_strategy_payoffs(options)
            else:
                # Optimized non-managed calculation
                total_payoffs = np.zeros(self.num_simulations)
                for opt in options:
                    strike = opt['strike']
                    premium = opt['premium']
                    is_call = opt['is_call']
                    is_long = opt['is_long']
                    
                    if is_call:
                        intrinsic = np.maximum(simulated_prices_at_exp - strike, 0)
                    else:
                        intrinsic = np.maximum(strike - simulated_prices_at_exp, 0)
                        
                    premium_100 = premium * 100
                    intrinsic_100 = intrinsic * 100
                    cost = self.transaction_cost_per_contract
                    
                    if is_long:
                        total_payoffs += (intrinsic_100 - premium_100 - cost)
                    else:
                        total_payoffs += (premium_100 - intrinsic_100 - cost)
            
            results.append(float(np.mean(total_payoffs) * discount_factor))
            
        return results

    def calculate_greeks_batch(self, strategies: List[List[Dict]]) -> List[Dict[str, float]]:
        """
        Calculate Greeks for multiple strategies in batch mode.
        """
        # Save original state
        original_price = self.current_price
        original_vol = self.volatility
        
        # 1. EV Base for all
        ev_base_list = self.calculate_expected_value_batch(strategies)
        
        # 2. Shift Price for Delta/Gamma
        ds = max(original_price * 0.005, 0.01)
        self.current_price = original_price + ds
        # No need to clear cache since params changed, lru_cache handles it
        ev_up_list = self.calculate_expected_value_batch(strategies)
        
        self.current_price = original_price - ds
        ev_down_list = self.calculate_expected_value_batch(strategies)
        
        # 3. Shift Vol for Vega
        self.current_price = original_price
        dv = 0.01 # 1% vol shift
        self.volatility = original_vol + dv
        ev_vega_list = self.calculate_expected_value_batch(strategies)
        
        # Restore original state
        self.volatility = original_vol
        
        results = []
        for i in range(len(strategies)):
            delta = (ev_up_list[i] - ev_down_list[i]) / (2 * ds)
            gamma = (ev_up_list[i] - 2 * ev_base_list[i] + ev_down_list[i]) / (ds ** 2)
            vega = (ev_vega_list[i] - ev_base_list[i]) / (dv * 100)
            
            results.append({
                "delta": float(delta / 100),
                "gamma": float(gamma / 100),
                "vega": float(vega)
            })
            
        return results

    def find_breakeven_from_simulations(self,
                                        simulated_prices: np.ndarray,
                                        total_payoffs: np.ndarray) -> List[float]:
        """
        Find breakeven points using the actual simulated data

        Args:
            simulated_prices: Array of simulated stock prices
            total_payoffs: Array of corresponding total payoffs

        Returns:
            List of estimated breakeven stock prices
        """
        # Create pairs of (price, payoff) and sort by price
        price_payoff_pairs = list(zip(simulated_prices, total_payoffs))
        price_payoff_pairs.sort(key=lambda x: x[0])

        prices = np.array([x[0] for x in price_payoff_pairs])
        payoffs = np.array([x[1] for x in price_payoff_pairs])

        # Find sign changes in payoffs (breakeven crossings)
        breakeven_points = []

        for i in range(len(payoffs) - 1):
            # Check if there's a sign change between consecutive points
            if payoffs[i] * payoffs[i + 1] < 0:  # Different signs (crossing zero)
                # Linear interpolation to find more precise breakeven point
                price1, payoff1 = prices[i], payoffs[i]
                price2, payoff2 = prices[i + 1], payoffs[i + 1]

                # Linear interpolation: find price where payoff = 0
                if payoff2 != payoff1:  # Avoid division by zero
                    breakeven_price = price1 - payoff1 * (price2 - price1) / (payoff2 - payoff1)
                    breakeven_points.append(breakeven_price)

        # Remove duplicates and sort
        if breakeven_points:
            breakeven_points = sorted(set(round(bp, 2) for bp in breakeven_points))

            # Cluster nearby points (within $1.00 of each other)
            clustered = []
            if breakeven_points:
                current_cluster = [breakeven_points[0]]

                for point in breakeven_points[1:]:
                    if point - current_cluster[-1] <= 1.0:
                        current_cluster.append(point)
                    else:
                        # Average the cluster
                        clustered.append(round(np.mean(current_cluster), 2))
                        current_cluster = [point]

                # Add the last cluster
                clustered.append(round(np.mean(current_cluster), 2))

                return clustered

        return breakeven_points

    @log_function
    def calculate_greeks(self, options: List[Dict]) -> Dict[str, float]:
        """
        Calculate strategy Greeks using Monte Carlo simulation and finite differences.
        Uses Common Random Numbers (CRN) for noise reduction.
        """
        # Save original state
        original_price = self.current_price
        original_vol = self.volatility
        
        # 1. EV(S) - Reuse cached paths if possible
        ev_base = self.calculate_expected_value(options)

        # 2. Delta & Gamma
        ds = max(original_price * 0.005, 0.01) # 0.5% shift
        
        # EV(S + ds)
        self.current_price = original_price + ds
        ev_plus = self.calculate_expected_value(options)
        
        # EV(S - ds)
        self.current_price = original_price - ds
        ev_minus = self.calculate_expected_value(options)
        
        delta = (ev_plus - ev_minus) / (2 * ds)
        gamma = (ev_plus - 2 * ev_base + ev_minus) / (ds ** 2)
        
        # Restore price
        self.current_price = original_price

        # 3. Vega
        dv = 0.01 # 1% IV shift
        self.volatility = original_vol + dv
        ev_vega = self.calculate_expected_value(options)
        
        # Restore volatility
        self.volatility = original_vol
        
        vega = (ev_vega - ev_base) / (dv * 100) # per 1% point
        
        return {
            "delta": float(delta / 100), # per share
            "gamma": float(gamma / 100),
            "vega": float(vega)
        }

    @log_function
    def analyze_strategy(self, options: List[Dict]) -> Dict:
        """
        Analyze an arbitrary multi-leg options strategy with full metrics

        Args:
            options: List of dictionaries, each containing:
                    - 'strike': Strike price
                    - 'premium': Option premium per share (always positive)
                    - 'is_call': True for Call, False for Put
                    - 'is_long': True for Long position, False for Short position
                    Note: Each entry in the list represents exactly 1 contract

        Returns:
            Dictionary with all analysis results
        """
        # Management parameters
        has_management = any(
            opt.get('take_profit_pct') is not None or 
            opt.get('stop_loss_pct') is not None or 
            opt.get('dte_close') is not None or
            (opt.get('planned_dte') is not None and opt.get('planned_dte') < self.dte)
            for opt in options
        )

        # Calculate detailed leg analysis
        leg_analysis = []
        total_transaction_costs = 0
        total_contracts = len(options)  # Each entry = 1 contract

        if has_management:
            simulated_prices, total_payoffs, initial_cashflow = self._calculate_managed_strategy_payoffs(options)
            # Managed payoffs already include everything, no need to re-calculate per leg for average
            # but we need leg_analysis for the UI.
            for i, option in enumerate(options):
                premium_per_contract = option['premium'] * 100
                transaction_cost_per_contract = self.transaction_cost_per_contract
                total_transaction_costs += transaction_cost_per_contract
                leg_analysis.append({
                    'leg_number': i + 1,
                    'type': 'Call' if option['is_call'] else 'Put',
                    'position': 'Long' if option['is_long'] else 'Short',
                    'strike': option['strike'],
                    'premium_per_share': option['premium'],
                    'premium_per_contract': premium_per_contract,
                    'transaction_cost': transaction_cost_per_contract,
                    'avg_payoff': 0.0, # Not easily available without significant change
                    'cashflow': (-premium_per_contract - transaction_cost_per_contract if option['is_long'] else premium_per_contract - transaction_cost_per_contract)
                })
        else:
            simulated_prices, total_payoffs, initial_cashflow = self._calculate_strategy_payoffs(options)
            # For non-managed, we can efficiently get leg payoffs since we have expiration prices
            for i, option in enumerate(options):
                leg_payoffs = self.calculate_single_option_payoff(
                    simulated_prices=simulated_prices,
                    strike=option['strike'],
                    premium=option['premium'],
                    is_call=option['is_call'],
                    is_long=option['is_long']
                )
                
                premium_per_contract = option['premium'] * 100
                transaction_cost_per_contract = self.transaction_cost_per_contract
                total_transaction_costs += transaction_cost_per_contract

                leg_analysis.append({
                    'leg_number': i + 1,
                    'type': 'Call' if option['is_call'] else 'Put',
                    'position': 'Long' if option['is_long'] else 'Short',
                    'strike': option['strike'],
                    'premium_per_share': option['premium'],
                    'premium_per_contract': premium_per_contract,
                    'transaction_cost': transaction_cost_per_contract,
                    'avg_payoff': np.mean(leg_payoffs),
                    'cashflow': (-premium_per_contract - transaction_cost_per_contract if option['is_long'] else premium_per_contract - transaction_cost_per_contract)
                })

        # Calculate overall statistics
        expected_value_raw = np.mean(total_payoffs)

        # Discount to present value
        discount_factor = np.exp(-self.risk_free_rate * self.time_to_expiration)
        expected_value = expected_value_raw * discount_factor

        # Probability analysis
        prob_profit = (total_payoffs > 0).mean() * 100
        prob_loss = (total_payoffs < 0).mean() * 100
        prob_breakeven = (np.abs(total_payoffs) < 1.0).mean() * 100  # Within $1 of breakeven

        # Risk metrics
        max_profit = np.max(total_payoffs)
        max_loss = np.min(total_payoffs)
        std_dev = np.std(total_payoffs)

        # Percentiles
        percentiles = np.percentile(total_payoffs, [5, 10, 25, 50, 75, 90, 95])

        # Find breakeven points using simulation data
        breakeven_points = self.find_breakeven_from_simulations(simulated_prices, total_payoffs)

        # Management stats (if applicable)
        management_stats = None
        if has_management and hasattr(self, '_last_exit_reasons'):
            # Aggregate exit reasons across all legs for each simulation
            # Since legs close together in this model, we can just look at the first leg that isn't Long if available
            # Or better, just count how many sims had ANY leg close via TP, SL, etc.
            management_stats = {
                'tp_count': int(np.any(self._last_exit_reasons == 1, axis=1).sum()),
                'sl_count': int(np.any(self._last_exit_reasons == 2, axis=1).sum()),
                'dc_count': int(np.any(self._last_exit_reasons == 3, axis=1).sum()),
                'pdte_count': int(np.any(self._last_exit_reasons == 4, axis=1).sum()),
                'exp_count': int(np.all(self._last_exit_reasons == 0, axis=1).sum()),
                'total_sims': self.num_simulations
            }

        return {
            # Main results
            'expected_value': expected_value,
            'expected_value_raw': expected_value_raw,
            'discount_factor': discount_factor,
            
            'management_stats': management_stats,

            # IV Correction info
            'raw_volatility': self.raw_volatility,
            'corrected_volatility': self.volatility,
            'iv_correction_factor': self.iv_correction_factor,
            'iv_correction_mode': self.iv_correction,

            # Cashflow (already includes transaction costs)
            'initial_cashflow': initial_cashflow,
            'net_debit': max(0, -initial_cashflow),
            'net_credit': max(0, initial_cashflow),
            'total_transaction_costs': total_transaction_costs,
            'total_contracts': total_contracts,

            # Probabilities
            'prob_profit': prob_profit,
            'prob_loss': prob_loss,
            'prob_breakeven': prob_breakeven,

            # Risk metrics
            'max_profit': max_profit,
            'max_loss': max_loss,
            'std_dev': std_dev,

            # Percentiles
            'percentiles': {
                '5%': percentiles[0],
                '10%': percentiles[1],
                '25%': percentiles[2],
                '50%': percentiles[3],
                '75%': percentiles[4],
                '90%': percentiles[5],
                '95%': percentiles[6]
            },

            # Breakeven from simulations
            'breakeven_points': breakeven_points,
            'avg_simulated_price': np.mean(simulated_prices),
            'simulated_price_std': np.std(simulated_prices),

            # Leg details
            'leg_analysis': leg_analysis,
            'num_legs': len(options),
            
            # Full data for analysis
            'simulated_prices': simulated_prices,
            'total_payoffs': total_payoffs
        }


def print_strategy_analysis(simulator: UniversalOptionsMonteCarloSimulator,
                            options: List[Dict],
                            strategy_name: str = "Multi-Leg Strategy") -> float:
    """
    Print comprehensive analysis for arbitrary options strategy
    """
    results = simulator.analyze_strategy(options)

    print("=" * 90)
    print(f"📊 MONTE-CARLO ANALYSIS: {strategy_name.upper()}")
    print("=" * 90)

    # Market parameters
    print(f"\n📈 MARKET PARAMETERS:")
    print(f"   Current Stock Price:      ${simulator.current_price:.2f}")
    print(f"   Market Implied Volatility: {results['raw_volatility'] * 100:.1f}%")
    print(f"   Corrected IV (simulation): {results['corrected_volatility'] * 100:.1f}%")
    print(
        f"   IV Correction Applied:     {results['iv_correction_factor'] * 100:.1f}% ({results['iv_correction_mode']})")
    print(f"   Days to Expiration:       {simulator.dte}")
    print(f"   Risk-free Rate:           {simulator.risk_free_rate * 100:.1f}%")
    print(f"   Dividend Yield:           {simulator.dividend_yield * 100:.1f}%")
    print(f"   Transaction Cost/Contract: ${simulator.transaction_cost_per_contract:.2f}")

    # Simulation settings
    print(f"\n⚙️  SIMULATION:")
    print(f"   Number of Simulations:    {simulator.num_simulations:,}")
    print(f"   Random Seed:              {simulator.random_seed or 'Random'}")
    print(f"   Discount Factor:          {results['discount_factor']:.6f}")

    # Strategy details
    print(f"\n🏗️ STRATEGY ({results['num_legs']} LEGS, {results['total_contracts']} CONTRACTS):")
    print("-" * 90)
    for leg in results['leg_analysis']:
        cashflow_sign = "+" if leg['cashflow'] > 0 else ""
        print(f"   Leg {leg['leg_number']:>2}: {leg['position']:>5} {leg['type']:>4} "
              f"@ ${leg['strike']:>6.0f} | "
              f"Premium: ${leg['premium_per_share']:>5.2f}/share | "
              f"Total: ${leg['premium_per_contract']:>7.0f} | "
              f"T-Cost: ${leg['transaction_cost']:>5.2f} | "
              f"Net: {cashflow_sign}${abs(leg['cashflow']):>7.0f}")

    # Cashflow overview
    print(f"\n💰 CASHFLOW:")
    print(f"   Total Transaction Costs:  ${results['total_transaction_costs']:.2f}")
    if results['initial_cashflow'] > 0:
        print(f"   Net Credit Received:      +${results['net_credit']:.2f}")
    elif results['initial_cashflow'] < 0:
        print(f"   Net Debit Paid:           -${results['net_debit']:.2f}")
    else:
        print(f"   Balanced Cashflow:        ${results['initial_cashflow']:.2f}")

    # Main results
    print(f"\n🎯 MONTE-CARLO RESULTS:")
    print(f"   Expected Value:           ${results['expected_value']:.2f}")
    print(f"   Expected Value (raw):     ${results['expected_value_raw']:.2f}")

    # Status interpretation
    if results['expected_value'] > 5.0:
        status_icon = "💚"
        status_text = f"POSITIVE (+${results['expected_value']:.2f})"
    elif results['expected_value'] < -5.0:
        status_icon = "🔴"
        status_text = f"NEGATIVE (${results['expected_value']:.2f})"
    else:
        status_icon = "⚖️"
        status_text = f"BALANCED (≈${results['expected_value']:.2f})"

    print(f"   {status_icon} Status:                {status_text}")

    # Probabilities
    print(f"\n📊 PROBABILITIES:")
    print(f"   Profit:                   {results['prob_profit']:>6.1f}%")
    print(f"   Loss:                     {results['prob_loss']:>6.1f}%")
    print(f"   Breakeven:                {results['prob_breakeven']:>6.1f}%")

    # Risk-reward
    print(f"\n⚖️  RISK-REWARD:")
    print(f"   Maximum Profit:           ${results['max_profit']:>8.2f}")
    print(f"   Maximum Loss:             ${results['max_loss']:>8.2f}")
    print(f"   Standard Deviation:       ${results['std_dev']:>8.2f}")

    if results['max_loss'] != 0:
        reward_risk = abs(results['max_profit'] / results['max_loss'])
        print(f"   Reward/Risk Ratio:        {reward_risk:>8.2f}")

    # Breakeven points from simulation data
    if results['breakeven_points']:
        print(f"\n⚡ BREAKEVEN POINTS (from simulations):")
        for i, bp in enumerate(results['breakeven_points'], 1):
            print(f"   Breakeven {i}:            ${bp:>8.2f}")
    else:
        print(f"\n⚡ BREAKEVEN POINTS: None found in simulation range")

    # Simulation details
    print(f"\n🎲 SIMULATION DETAILS:")
    print(f"   Avg Simulated Price:      ${results['avg_simulated_price']:>8.2f}")
    print(f"   Price Std Dev (Expected Move): ${results['simulated_price_std']:>8.2f}")

    print("=" * 90)

    return results['expected_value']


if __name__ == "__main__":
    from config import *

    # von spreads_calculation übernommen
    monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations= NUM_SIMULATIONS, #NUM_SIMULATIONS,
        random_seed=RANDOM_SEED,
        current_price=170.94,
        dte=63,
        volatility=0.42,
        risk_free_rate=RISK_FREE_RATE,
        dividend_yield=0,
        iv_correction='auto' # 'auto'
    )

    options = [
        # sell option
        {
            'strike': 150,
            'premium': 3.47,
            'is_call': False,
            'is_long': False
        },

        # buy option
        {
            'strike': 145,
            'premium': 1.72,
            'is_call': False,
            'is_long': True
        }
    ]

    expected_value = monte_carlo_simulator.calculate_expected_value(options=options)
    print(f"monte_carlo_simulator.volatility: {monte_carlo_simulator.volatility}")
    print(f"expected_value: {expected_value}")

    print(monte_carlo_simulator)


    # import matplotlib.pyplot as plt
    # import numpy as np
    #
    # # Annahme: UniversalOptionsMonteCarloSimulator ist bereits definiert
    # # Hier wird nur der relevante Teil für die Simulationen und das Plotting ergänzt
    #
    # # Parameter für die Simulation
    # current_price = 170.94
    # dte = 63
    # volatility = 0.42
    # risk_free_rate = RISK_FREE_RATE  # Annahme: RISK_FREE_RATE ist definiert
    # dividend_yield = 0
    # random_seed = RANDOM_SEED  # Annahme: RISK_FREE_RATE und RANDOM_SEED sind definiert
    #
    # # Optionen
    # options = [
    #     # sell option
    #     {
    #         'strike': 150,
    #         'premium': 3.47,
    #         'is_call': False,
    #         'is_long': False
    #     },
    #     # buy option
    #     {
    #         'strike': 145,
    #         'premium': 1.72,
    #         'is_call': False,
    #         'is_long': True
    #     }
    # ]
    #
    # # Anzahl der Simulationen variieren
    # num_simulations_list = np.logspace(1, 5, 50).astype(int)  # 10 bis 100.000 Simulationen, logarithmisch verteilt
    # expected_values = []
    #
    # for num_simulations in num_simulations_list:
    #     monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
    #         num_simulations=num_simulations,
    #         random_seed=random_seed,
    #         current_price=current_price,
    #         dte=dte,
    #         volatility=volatility,
    #         risk_free_rate=risk_free_rate,
    #         dividend_yield=dividend_yield,
    #         iv_correction='auto'
    #     )
    #
    #     expected_value = monte_carlo_simulator.calculate_expected_value(options=options)
    #     expected_values.append(expected_value)
    #     print(f"Num Simulations: {num_simulations}, Expected Value: {expected_value}")
    #
    # # Plot der Ergebnisse
    # plt.figure(figsize=(10, 6))
    # plt.plot(num_simulations_list, expected_values, marker='o')
    # plt.xscale('log')
    # plt.xlabel('Anzahl der Simulationen (log Skala)')
    # plt.ylabel('Erwartungswert')
    # plt.title('Erwartungswert in Abhängigkeit der Anzahl der Simulationen')
    # plt.grid(True, which="both", ls="--")
    # plt.show()

