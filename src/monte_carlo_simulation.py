import numpy as np
import pandas as pd
from typing import List, Dict, Tuple

#todo parameter für commisionen hinzufügen bei erwartungswert
#todo parameter für iv korrektur in abhänigkeit von dte und index vs aktienoption hinzufügen

class UniversalOptionsMonteCarloSimulator:
    """
    Universelle Monte-Carlo-Simulation für beliebige Multi-Leg-Optionsstrategien

    Die Logik ist einfach:
    1. Jede Option hat bei Verfall nur ihren intrinsischen Wert
    2. Long-Positionen: Zahle Prämie heute, erhalte intrinsischen Wert bei Verfall
    3. Short-Positionen: Erhalte Prämie heute, zahle intrinsischen Wert bei Verfall
    4. Erwartungswert = Durchschnitt aller möglichen Payoffs (abgezinst)
    """

    def __init__(self,
                 current_price: float,
                 volatility: float,
                 dte: int,
                 risk_free_rate: float = 0.03,
                 dividend_yield: float = 0.00,
                 num_simulations: int = 100000,
                 random_seed: int = None):
        """
        Initialisiert den universellen Monte-Carlo-Simulator

        Args:
            current_price: Aktueller Aktienkurs
            volatility: Implizite Volatilität (z.B. 0.35 für 35%)
            dte: Tage bis Verfall
            risk_free_rate: Risikofreier Zinssatz
            dividend_yield: Dividendenrendite
            num_simulations: Anzahl Monte-Carlo-Simulationen
            random_seed: Seed für reproduzierbare Ergebnisse
        """
        self.current_price = current_price
        self.volatility = volatility
        self.dte = dte
        self.risk_free_rate = risk_free_rate
        self.dividend_yield = dividend_yield
        self.num_simulations = num_simulations
        self.random_seed = random_seed
        self.time_to_expiration = dte / 365

        # Random Seed setzen
        if random_seed is not None:
            np.random.seed(random_seed)

    def simulate_stock_prices(self) -> np.ndarray:
        """
        Simuliert Aktienpreise bei Verfall mit geometrischer Brown'scher Bewegung

        Verwendet risiko-neutrale Bewertung für Optionspreismodelle
        """
        # Für Monte-Carlo-Optionsbewertung: Risiko-neutrale Drift
        drift = self.risk_free_rate - self.dividend_yield

        # Reset Random Seed für konsistente Ergebnisse
        if self.random_seed is not None:
            np.random.seed(self.random_seed)

        # Normalverteilte Zufallsschocks
        random_shocks = np.random.standard_normal(self.num_simulations)

        # Lognormale Preissimulation: S(T) = S(0) * exp((r-q-σ²/2)*T + σ*√T*ε)
        log_returns = ((drift - 0.5 * self.volatility ** 2) * self.time_to_expiration +
                       self.volatility * np.sqrt(self.time_to_expiration) * random_shocks)

        simulated_prices = self.current_price * np.exp(log_returns)

        return simulated_prices

    def calculate_option_intrinsic_value(self,
                                         stock_price: float,
                                         strike: float,
                                         is_call: bool) -> float:
        """
        Berechnet intrinsischen Wert einer Option bei Verfall

        Args:
            stock_price: Aktienkurs bei Verfall
            strike: Strike-Preis der Option
            is_call: True für Call, False für Put

        Returns:
            Intrinsischer Wert der Option
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
        Berechnet Payoff für eine einzelne Option über alle Simulationen

        Args:
            simulated_prices: Array mit simulierten Aktienpreisen bei Verfall
            strike: Strike-Preis der Option
            premium: Gezahlte/erhaltene Prämie (immer positiv angeben)
            is_call: True für Call-Option, False für Put-Option
            is_long: True für Long-Position (gekauft), False für Short-Position (verkauft)

        Returns:
            Array mit Payoffs für jede Simulation
        """
        # Intrinsische Werte bei Verfall für alle Simulationen
        if is_call:
            intrinsic_values = np.maximum(simulated_prices - strike, 0)
        else:
            intrinsic_values = np.maximum(strike - simulated_prices, 0)

        # Payoff-Berechnung je nach Position
        if is_long:
            # Long: Zahle Prämie heute, erhalte intrinsischen Wert bei Verfall
            payoffs = intrinsic_values - premium
        else:
            # Short: Erhalte Prämie heute, zahle intrinsischen Wert bei Verfall
            payoffs = premium - intrinsic_values

        return payoffs

    def analyze_strategy(self, options: List[Dict]) -> Dict:
        """
        Analysiert eine beliebige Multi-Leg-Optionsstrategie

        Args:
            options: Liste von Dictionaries, jedes mit:
                    - 'strike': Strike-Preis
                    - 'premium': Optionsprämie (immer positiv)
                    - 'is_call': True für Call, False für Put
                    - 'is_long': True für Long-Position, False für Short-Position

        Returns:
            Dictionary mit allen Analyseergebnissen
        """
        # Simuliere Aktienpreise bei Verfall
        simulated_prices = self.simulate_stock_prices()

        # Gesamtpayoffs initialisieren
        total_payoffs = np.zeros(self.num_simulations)

        # Netto-Cashflow zu Beginn berechnen
        initial_cashflow = 0

        # Berechne Payoff für jedes Options-Leg
        leg_analysis = []
        for i, option in enumerate(options):
            # Einzelnes Leg analysieren
            leg_payoffs = self.calculate_single_option_payoff(
                simulated_prices=simulated_prices,
                strike=option['strike'],
                premium=option['premium'],
                is_call=option['is_call'],
                is_long=option['is_long']
            )

            # Zu Gesamtpayoff hinzufügen
            total_payoffs += leg_payoffs

            # Cashflow-Tracking
            if option['is_long']:
                initial_cashflow -= option['premium']  # Zahlen für Long
            else:
                initial_cashflow += option['premium']  # Erhalten für Short

            # Leg-Details für Analyse speichern
            leg_info = {
                'leg_number': i + 1,
                'type': 'Call' if option['is_call'] else 'Put',
                'position': 'Long' if option['is_long'] else 'Short',
                'strike': option['strike'],
                'premium': option['premium'],
                'avg_payoff': np.mean(leg_payoffs),
                'cashflow': -option['premium'] if option['is_long'] else option['premium']
            }
            leg_analysis.append(leg_info)

        # Gesamtstatistiken berechnen
        expected_value_raw = np.mean(total_payoffs)

        # Abzinsung auf heutigen Wert
        discount_factor = np.exp(-self.risk_free_rate * self.time_to_expiration)
        expected_value = expected_value_raw * discount_factor

        # Wahrscheinlichkeitsanalyse
        prob_profit = (total_payoffs > 0).mean() * 100
        prob_loss = (total_payoffs < 0).mean() * 100
        prob_breakeven = (np.abs(total_payoffs) < 0.01).mean() * 100

        # Risk-Metriken
        max_profit = np.max(total_payoffs)
        max_loss = np.min(total_payoffs)
        std_dev = np.std(total_payoffs)

        # Percentile
        percentiles = np.percentile(total_payoffs, [5, 10, 25, 50, 75, 90, 95])

        # Breakeven-Punkte schätzen
        breakeven_points = self._estimate_breakeven_points(options)

        return {
            # Hauptergebnisse
            'expected_value': expected_value,
            'expected_value_raw': expected_value_raw,
            'discount_factor': discount_factor,

            # Cashflow
            'initial_cashflow': initial_cashflow,
            'net_debit': max(0, -initial_cashflow),
            'net_credit': max(0, initial_cashflow),

            # Wahrscheinlichkeiten
            'prob_profit': prob_profit,
            'prob_loss': prob_loss,
            'prob_breakeven': prob_breakeven,

            # Risk-Metriken
            'max_profit': max_profit,
            'max_loss': max_loss,
            'std_dev': std_dev,

            # Percentile
            'percentiles': {
                '5%': percentiles[0],
                '10%': percentiles[1],
                '25%': percentiles[2],
                '50%': percentiles[3],
                '75%': percentiles[4],
                '90%': percentiles[5],
                '95%': percentiles[6]
            },

            # Breakeven & Simulation
            'breakeven_points': breakeven_points,
            'avg_simulated_price': np.mean(simulated_prices),
            'simulated_price_std': np.std(simulated_prices),

            # Leg-Details
            'leg_analysis': leg_analysis,
            'num_legs': len(options)
        }

    def _estimate_breakeven_points(self, options: List[Dict]) -> List[float]:
        """
        Schätzt Breakeven-Punkte durch Abtasten des Preisbereichs
        """
        # Erweiterten Preisbereich definieren
        price_range = np.linspace(
            self.current_price * 0.3,  # 30% unter aktuellem Preis
            self.current_price * 1.7,  # 70% über aktuellem Preis
            2000  # Höhere Auflösung für genauere Breakevens
        )

        breakeven_points = []

        for price in price_range:
            total_payoff = 0

            # Payoff bei diesem spezifischen Preis berechnen
            for option in options:
                # Intrinsischer Wert
                intrinsic = self.calculate_option_intrinsic_value(
                    price, option['strike'], option['is_call']
                )

                # Leg-Payoff
                if option['is_long']:
                    leg_payoff = intrinsic - option['premium']
                else:
                    leg_payoff = option['premium'] - intrinsic

                total_payoff += leg_payoff

            # Breakeven-Toleranz: ±0.02
            if abs(total_payoff) < 0.02:
                breakeven_points.append(round(price, 2))

        # Duplikate entfernen, sortieren und clustern
        if breakeven_points:
            # Cluster nahe beieinanderliegende Punkte
            breakeven_points = sorted(set(breakeven_points))
            clustered = []
            current_cluster = [breakeven_points[0]]

            for point in breakeven_points[1:]:
                if point - current_cluster[-1] < 1.0:  # Weniger als $1 Unterschied
                    current_cluster.append(point)
                else:
                    # Cluster-Durchschnitt nehmen
                    clustered.append(round(sum(current_cluster) / len(current_cluster), 2))
                    current_cluster = [point]

            # Letzten Cluster hinzufügen
            clustered.append(round(sum(current_cluster) / len(current_cluster), 2))
            return clustered

        return []


def print_strategy_analysis(simulator: UniversalOptionsMonteCarloSimulator,
                            options: List[Dict],
                            strategy_name: str = "Multi-Leg Strategy") -> float:
    """
    Druckt umfassende Analyse für beliebige Optionsstrategie
    """
    results = simulator.analyze_strategy(options)

    print("=" * 90)
    print(f"📊 MONTE-CARLO ANALYSE: {strategy_name.upper()}")
    print("=" * 90)

    # Marktparameter
    print(f"\n📈 MARKTPARAMETER:")
    print(f"   Aktueller Aktienkurs:     ${simulator.current_price:.2f}")
    print(f"   Implizite Volatilität:    {simulator.volatility * 100:.1f}%")
    print(f"   Tage bis Verfall:         {simulator.dte}")
    print(f"   Risikofreier Zins:        {simulator.risk_free_rate * 100:.1f}%")
    print(f"   Dividendenrendite:        {simulator.dividend_yield * 100:.1f}%")

    # Simulationseinstellungen
    print(f"\n⚙️  SIMULATION:")
    print(f"   Anzahl Simulationen:      {simulator.num_simulations:,}")
    print(f"   Random Seed:              {simulator.random_seed or 'Zufällig'}")
    print(f"   Abzinsungsfaktor:         {results['discount_factor']:.6f}")

    # Strategiedetails
    print(f"\n🏗️ STRATEGIE ({results['num_legs']} LEGS):")
    print("-" * 90)
    for leg in results['leg_analysis']:
        cashflow_sign = "+" if leg['cashflow'] > 0 else ""
        print(f"   Leg {leg['leg_number']:>2}: {leg['position']:>5} {leg['type']:>4} "
              f"@ ${leg['strike']:>6.0f} | Prämie: {cashflow_sign}${leg['cashflow']:>6.2f} | "
              f"Ø Payoff: ${leg['avg_payoff']:>7.2f}")

    # Cashflow-Übersicht
    print(f"\n💰 CASHFLOW:")
    if results['initial_cashflow'] > 0:
        print(f"   Netto-Kredit erhalten:    +${results['net_credit']:.2f}")
    elif results['initial_cashflow'] < 0:
        print(f"   Netto-Debit gezahlt:      -${results['net_debit']:.2f}")
    else:
        print(f"   Ausgeglichener Cashflow:  ${results['initial_cashflow']:.2f}")

    # Hauptergebnisse
    print(f"\n🎯 MONTE-CARLO ERGEBNISSE:")
    print(f"   Erwartungswert:           ${results['expected_value']:.2f}")
    print(f"   Erwartungswert (roh):     ${results['expected_value_raw']:.2f}")

    # Status-Interpretation
    if results['expected_value'] > 0.5:
        status_icon = "💚"
        status_text = f"POSITIV (+${results['expected_value']:.2f})"
    elif results['expected_value'] < -0.5:
        status_icon = "🔴"
        status_text = f"NEGATIV (${results['expected_value']:.2f})"
    else:
        status_icon = "⚖️"
        status_text = f"AUSGEGLICHEN (≈${results['expected_value']:.2f})"

    print(f"   {status_icon} Status:                {status_text}")

    # Wahrscheinlichkeiten
    print(f"\n📊 WAHRSCHEINLICHKEITEN:")
    print(f"   Gewinn:                   {results['prob_profit']:>6.1f}%")
    print(f"   Verlust:                  {results['prob_loss']:>6.1f}%")
    print(f"   Breakeven:                {results['prob_breakeven']:>6.1f}%")

    # Risk-Reward
    print(f"\n⚖️  RISK-REWARD:")
    print(f"   Maximaler Gewinn:         ${results['max_profit']:>8.2f}")
    print(f"   Maximaler Verlust:        ${results['max_loss']:>8.2f}")
    print(f"   Standardabweichung:       ${results['std_dev']:>8.2f}")

    if results['max_loss'] != 0:
        reward_risk = abs(results['max_profit'] / results['max_loss'])
        print(f"   Reward/Risk Ratio:        {reward_risk:>8.2f}")

    # Breakeven-Punkte
    if results['breakeven_points']:
        print(f"\n⚡ BREAKEVEN-PUNKTE:")
        for i, bp in enumerate(results['breakeven_points'], 1):
            print(f"   Breakeven {i}:            ${bp:>8.2f}")

    # Simulation Details
    print(f"\n🎲 SIMULATION DETAILS:")
    print(f"   Ø Simulierter Preis:      ${results['avg_simulated_price']:>8.2f}")
    print(f"   Preis-Standardabw. Expected Move:       ${results['simulated_price_std']:>8.2f}")

    print("=" * 90)

    return results['expected_value']


if __name__ == "__main__":
    print("🧪 UNIVERSELLE MONTE-CARLO OPTIONSSIMULATION")
    print("=" * 80)

    # Simulator initialisieren
    simulator = UniversalOptionsMonteCarloSimulator(
        current_price=227.00,
        volatility= 0.35,#0.336,
        dte=54,
        risk_free_rate=0.03,
        dividend_yield=0.00,
        num_simulations=100000,
        random_seed=42
    )

    # Iron Condor
    iron_condor_options = [
        # Long Put
        {
            'strike': 200,
            'premium': 2.50,#2.50,
            'is_call': False,
            'is_long': True
        },
        # Short Put
        {
            'strike': 210,
            'premium': 5, #4.85
            'is_call': False,
            'is_long': False
        },
        # Short Call
        {
            'strike': 250,
            'premium': 5,#4.69,
            'is_call': True,
            'is_long': False
        },
        # Long Call
        {
            'strike': 260,
            'premium': 2.85,
            'is_call': True,
            'is_long': True
        }
    ]

    # Analyse durchführen
    expected_value = print_strategy_analysis(
        simulator,
        iron_condor_options,
        "Iron Condor"
    )

    print(f"\n🔢 FINALER ERWARTUNGSWERT: ${expected_value:.2f}")

