import logging
import os
import streamlit as st
from src.logger_config import setup_logging
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

# Enable logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Page header
st.title("Expected Value of Options Strategy")
st.markdown("""
    This app simulates the expected value of an options strategy using Monte-Carlo simulation.
    Enter the parameters and start the calculation. Not running just a template at the moment.
""")

# --- Simulation Parameters ---
with st.expander("Simulation Parameters", expanded=True):
    col1, col2 = st.columns(2)
    with col1:
        num_simulations = st.number_input(
            "Number of Simulations", min_value=1000, value=100000, step=1000
        )
        current_price = st.number_input(
            "Current Stock Price", min_value=0.01, value=170.94, step=0.01
        )
        dte = st.number_input("Days to Expiration (DTE)", min_value=1, value=63, step=1)
        volatility = st.number_input("Volatility", min_value=0.01, value=0.42, step=0.01)
        risk_free_rate = st.number_input(
            "Risk-Free Rate", min_value=0.0, value=0.03, step=0.001
        )
        random_seed = st.number_input("Random Seed", min_value=1, value=42, step=1)
    with col2:
        dividend_yield = st.number_input(
            "Dividend Yield", min_value=0.0, value=0.0, step=0.001
        )
        transaction_cost_per_contract = st.number_input(
            "Transaction Cost per Contract", min_value=0.0, value=2.0, step=0.1
        )
        iv_correction = st.selectbox("IV Correction", ["auto", "none"], index=0)

# --- Options Input: Dynamic Addition and Deletion ---
st.subheader("Options Parameters")

# Initialize session state for options if not present
if "options" not in st.session_state:
    st.session_state.options = [
        {"strike": 150.0, "premium": 3.47, "type": "Put Sold"},
        {"strike": 145.0, "premium": 1.72, "type": "Put Sold"},
    ]

# Display and edit options
for i, option in enumerate(st.session_state.options):
    with st.expander(f"Option {i+1}", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            option["strike"] = st.number_input(
                f"Strike {i+1}", min_value=0.01, value=option["strike"], step=0.5
            )
            option["premium"] = st.number_input(
                f"Premium {i+1}", min_value=0.01, value=option["premium"], step=0.01
            )
        with col2:
            # Radio button for option type (only one can be selected)
            option_type = st.radio(
                f"Type {i+1}",
                ["Call Bought", "Call Sold", "Put Bought", "Put Sold"],
                index=["Call Bought", "Call Sold", "Put Bought", "Put Sold"].index(option["type"])
            )
            option["type"] = option_type
            st.markdown(f"**Selected:** {option['type']}")

        # Delete option button
        if st.button(f"Delete Option {i+1}"):
            st.session_state.options.pop(i)
            st.rerun()

# Button to add more options
if st.button("Add Another Option"):
    st.session_state.options.append(
        {"strike": 150.0, "premium": 3.47, "type": "Put Sold"}
    )
    st.rerun()

# --- Run Simulation ---
if st.button("Start Simulation"):
    with st.spinner("Calculating expected value..."):
        try:
            # Convert option types to is_call and is_long
            options = []
            for option in st.session_state.options:
                is_call = option["type"] in ["Call Bought", "Call Sold"]
                is_long = option["type"] in ["Call Bought", "Put Bought"]
                options.append({
                    "strike": option["strike"],
                    "premium": option["premium"],
                    "is_call": is_call,
                    "is_long": is_long,
                })

            monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
                num_simulations=num_simulations,
                random_seed=random_seed,
                current_price=current_price,
                dte=dte,
                volatility=volatility,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
                iv_correction=iv_correction,
            )

            expected_value = monte_carlo_simulator.calculate_expected_value(options=options)

            # --- Display Results ---
            st.success("Simulation completed!")
            st.subheader("Results")
            st.markdown(f"""
                | Parameter                     | Value                     |
                |-------------------------------|--------------------------|
                | **Expected Value**            | {expected_value:.2f}     |
                | Current Stock Price           | {current_price:.2f}      |
                | Raw Volatility                | {volatility:.4f}         |
                | Days to Expiration (DTE)      | {dte}                    |
                | Risk-Free Rate                | {risk_free_rate:.4f}     |
                | Dividend Yield                | {dividend_yield:.4f}     |
                | Number of Simulations         | {num_simulations:,}      |
                | Random Seed                   | {random_seed}            |
                | Transaction Cost per Contract | {transaction_cost_per_contract:.2f} |
                | IV Correction                 | {iv_correction}          |
                | Corrected Volatility          | {monte_carlo_simulator.volatility:.6f} |
                | IV Correction Factor          | {monte_carlo_simulator.iv_correction_factor:.6f} |
                | Time to Expiration (Years)    | {monte_carlo_simulator.time_to_expiration:.6f} |
            """)

            # --- Option Strategy Summary ---
            st.subheader("Option Strategy Summary")
            for i, option in enumerate(st.session_state.options):
                st.markdown(f"""
                    **Option {i+1}:**
                    - Strike: {option['strike']:.2f}
                    - Premium: {option['premium']:.2f}
                    - Type: {option['type']}
                """)

        except Exception as e:
            st.error(f"Error during simulation: {e}")
            logger.error(f"Simulation error: {e}")
