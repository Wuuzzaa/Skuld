import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Union

from config import TRANSACTION_COST_PER_CONTRACT, RANDOM_SEED, NUM_SIMULATIONS, RISK_FREE_RATE, IV_CORECTION_MODE


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
                 iv_correction: Union[str, float] = IV_CORECTION_MODE):
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

    def simulate_stock_prices(self) -> np.ndarray:
        """
        Simulate stock prices at expiration using geometric Brownian motion

        Uses risk-neutral valuation for options pricing models with corrected IV
        """
        # For Monte-Carlo option valuation: Risk-neutral drift
        drift = self.risk_free_rate - self.dividend_yield

        # Reset random seed for consistent results
        if self.random_seed is not None:
            np.random.seed(self.random_seed)

        # Normally distributed random shocks
        random_shocks = np.random.standard_normal(self.num_simulations)

        # Lognormal price simulation using CORRECTED volatility
        # S(T) = S(0) * exp((r-q-σ²/2)*T + σ*√T*ε)
        log_returns = ((drift - 0.5 * self.volatility ** 2) * self.time_to_expiration +
                       self.volatility * np.sqrt(self.time_to_expiration) * random_shocks)

        simulated_prices = self.current_price * np.exp(log_returns)

        return simulated_prices

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

    def calculate_expected_value(self, options: List[Dict]) -> float:
        """
        Calculate only the expected value of the strategy (fast computation)

        Args:
            options: List of option dictionaries

        Returns:
            Expected value of the strategy (discounted to present value)
        """
        _, total_payoffs, _ = self._calculate_strategy_payoffs(options)

        # Calculate expected value
        expected_value_raw = np.mean(total_payoffs)

        # Discount to present value
        discount_factor = np.exp(-self.risk_free_rate * self.time_to_expiration)
        self.expected_value = expected_value_raw * discount_factor

        return self.expected_value

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
        # Get basic payoff calculations
        simulated_prices, total_payoffs, initial_cashflow = self._calculate_strategy_payoffs(options)

        # Calculate detailed leg analysis
        leg_analysis = []
        total_transaction_costs = 0
        total_contracts = len(options)  # Each entry = 1 contract

        for i, option in enumerate(options):
            # Analyze single leg for detailed reporting
            leg_payoffs = self.calculate_single_option_payoff(
                simulated_prices=simulated_prices,
                strike=option['strike'],
                premium=option['premium'],
                is_call=option['is_call'],
                is_long=option['is_long']
            )

            # Cashflow calculations for reporting
            premium_per_contract = option['premium'] * 100
            transaction_cost_per_contract = self.transaction_cost_per_contract
            total_transaction_costs += transaction_cost_per_contract

            # Store leg details for analysis
            leg_info = {
                'leg_number': i + 1,
                'type': 'Call' if option['is_call'] else 'Put',
                'position': 'Long' if option['is_long'] else 'Short',
                'strike': option['strike'],
                'premium_per_share': option['premium'],
                'premium_per_contract': premium_per_contract,
                'transaction_cost': transaction_cost_per_contract,
                'avg_payoff': np.mean(leg_payoffs),
                'cashflow': (-premium_per_contract - transaction_cost_per_contract
                             if option['is_long']
                             else premium_per_contract - transaction_cost_per_contract)
            }
            leg_analysis.append(leg_info)

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

        return {
            # Main results
            'expected_value': expected_value,
            'expected_value_raw': expected_value_raw,
            'discount_factor': discount_factor,

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
            'num_legs': len(options)
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

