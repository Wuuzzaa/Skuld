import logging
import os
import streamlit as st
from src.logger_config import setup_logging
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator


# enable logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Page header
st.title("Expected Value")

st.markdown("""
        Diese App simuliert den Erwartungswert einer Optionsstrategie mithilfe einer Monte-Carlo-Simulation.
        Gib die Parameter ein und starte die Berechnung.
    """)

# Inputs für die Simulation
with st.expander("Simulationsparameter", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        num_simulations = st.number_input("Anzahl Simulationen", min_value=1000, value=100000, step=1000)
        current_price = st.number_input("Aktueller Aktienpreis", min_value=0.01, value=170.94, step=0.01)
        dte = st.number_input("Tage bis Verfall (DTE)", min_value=1, value=63, step=1)
        volatility = st.number_input("Volatilität", min_value=0.01, value=0.42, step=0.01)
        risk_free_rate = st.number_input("Risikofreier Zinssatz", min_value=0.0, value=0.03, step=0.001)
        random_seed = st.number_input("Random Seed", min_value=1, value=42, step=1)
    with col2:
        dividend_yield = st.number_input("Dividendenrendite", min_value=0.0, value=0.0, step=0.001)
        transaction_cost_per_contract = st.number_input("Transaktionskosten pro Kontrakt", min_value=0.0, value=2.0, step=0.1)
        iv_correction = st.selectbox("IV-Korrektur", ["auto", "none"], index=0)

# Inputs für die Optionen
with st.expander("Optionsparameter", expanded=True):
    st.markdown("**Verkaufte Option**")
    col3, col4 = st.columns(2)
    with col3:
        sold_strike = st.number_input("Strike (verkauft)", min_value=0.01, value=150.0, step=0.5)
        sold_premium = st.number_input("Prämie (verkauft)", min_value=0.01, value=3.47, step=0.01)
    with col4:
        sold_is_call = st.checkbox("Call (verkauft)", value=False)
        sold_is_long = st.checkbox("Long (verkauft)", value=False)

    st.markdown("**Gekaufte Option**")
    col5, col6 = st.columns(2)
    with col5:
        bought_strike = st.number_input("Strike (gekauft)", min_value=0.01, value=145.0, step=0.5)
        bought_premium = st.number_input("Prämie (gekauft)", min_value=0.01, value=1.72, step=0.01)
    with col6:
        bought_is_call = st.checkbox("Call (gekauft)", value=False)
        bought_is_long = st.checkbox("Long (gekauft)", value=True)

# Button zum Starten der Simulation
if st.button("Simulation starten"):
    with st.spinner("Berechne Erwartungswert..."):
        # Initialisiere den Simulator
        monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
            num_simulations=num_simulations,
            random_seed=random_seed,
            current_price=current_price,
            dte=dte,
            volatility=volatility,
            risk_free_rate=risk_free_rate,
            dividend_yield=dividend_yield,
            iv_correction=iv_correction
        )

        # Definiere die Optionen
        options = [
            {
                'strike': sold_strike,
                'premium': sold_premium,
                'is_call': sold_is_call,
                'is_long': sold_is_long
            },
            {
                'strike': bought_strike,
                'premium': bought_premium,
                'is_call': bought_is_call,
                'is_long': bought_is_long
            }
        ]

        # Führe die Berechnung durch
        expected_value = monte_carlo_simulator.calculate_expected_value(options=options)

        # Ergebnisse anzeigen
        st.success("Simulation abgeschlossen!")
        st.subheader("Ergebnisse")
        st.markdown(f"""
            | Parameter                     | Wert                     |
            |-------------------------------|--------------------------|
            | **Erwartungswert**            | {expected_value:.2f}     |
            | Aktueller Aktienpreis         | {current_price:.2f}      |
            | Rohvolatilität                | {volatility:.4f}         |
            | Tage bis Verfall (DTE)        | {dte}                    |
            | Risikofreier Zinssatz         | {risk_free_rate:.4f}     |
            | Dividendenrendite             | {dividend_yield:.4f}     |
            | Anzahl Simulationen           | {num_simulations:,}      |
            | Random Seed                   | {random_seed}            |
            | Transaktionskosten pro Kontrakt | {transaction_cost_per_contract:.2f} |
            | IV-Korrektur                  | {iv_correction}          |
            | Korrigierte Volatilität       | {monte_carlo_simulator.volatility:.6f} |
            | IV-Korrekturfaktor            | {monte_carlo_simulator.iv_correction_factor:.6f} |
            | Zeit bis Verfall (Jahre)      | {monte_carlo_simulator.time_to_expiration:.6f} |
        """, unsafe_allow_html=False)