import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator
from config import RANDOM_SEED, NUM_SIMULATIONS, RISK_FREE_RATE, IV_CORRECTION_MODE, TRANSACTION_COST_PER_CONTRACT
import logging
import os

# Setup logging
logger = logging.getLogger(os.path.basename(__file__))

# --- Data Transfer Logic ---
if 'mc_transfer_data' in st.session_state:
    data = st.session_state.pop('mc_transfer_data')
    st.session_state['mc_current_price'] = data['underlying_price']
    st.session_state['mc_volatility'] = data['volatility']
    st.session_state['mc_dte'] = data['dte']
    st.session_state['mc_take_profit'] = data.get('take_profit', 0)
    st.session_state['mc_stop_loss'] = data.get('stop_loss', 0)
    st.session_state['mc_dte_close'] = data.get('dte_close', 0)
    st.session_state.legs = data['legs']
    st.toast("Strategie aus Details übernommen!", icon="📥")

st.set_page_config(page_title="Monte Carlo Debug", page_icon="🎲", layout="wide")

st.title("🎲 Monte Carlo Simulation Debug")
st.markdown("""
Diese Seite dient zum manuellen Testen und Debuggen der Monte-Carlo-Simulation für Optionsstrategien.
Du kannst hier alle Parameter frei konfigurieren und die detaillierte Analyse einsehen.

### 📖 Kurzanleitung
1. **Global Settings**: Stelle den aktuellen Aktienkurs, die Volatilität und die Laufzeit (DTE) in der Seitenleiste ein.
2. **Strategy Construction**: Füge "Legs" (Optionen) hinzu. Wähle zwischen Call/Put und Long/Short.
3. **Management**: (Optional) Setze Stop-Loss, Take-Profit oder einen automatischen Schließtag (DTE Close).
4. **Ausführung**: Klicke auf "Run Simulation", um tausende Pfade zu berechnen und die statistische Auswertung zu sehen.
""")

# --- Sidebar: Global Settings ---
with st.sidebar:
    st.header("Global Settings")
    
    col1, col2 = st.columns(2)
    with col1:
        current_price = st.number_input("Underlying Price", value=float(st.session_state.get('mc_current_price', 100.0)), step=1.0, help="Aktueller Kurs des Basiswerts (z.B. Aktie oder Index).", key="mc_cp_input")
        volatility = st.number_input("Implied Volatility (IV)", value=float(st.session_state.get('mc_volatility', 0.30)), step=0.01, format="%.2f", help="Die erwartete Schwankungsbreite des Basiswerts pro Jahr.", key="mc_iv_input")
    with col2:
        dte = st.number_input("Days to Expiration (DTE)", value=int(st.session_state.get('mc_dte', 45)), step=1, help="Anzahl der Tage bis zum Verfall der Optionen.", key="mc_dte_input")
        risk_free_rate = st.number_input("Risk Free Rate", value=RISK_FREE_RATE, step=0.001, format="%.3f", help="Der risikofreie Zinssatz (Marktzins).")

dividend_yield = st.number_input("Dividend Yield", value=0.0, step=0.01, format="%.2f", help="Erwartete Dividendenrendite des Basiswerts.")
    
st.divider()
st.subheader("Simulation Settings")
num_simulations = st.number_input("Number of Simulations", value=NUM_SIMULATIONS, step=1000, help="Anzahl der simulierten Pfade. Höhere Werte erhöhen die Genauigkeit, dauern aber länger.")
seed = st.number_input("Random Seed", value=RANDOM_SEED, step=1, help="Startwert für den Zufallsgenerator (für reproduzierbare Ergebnisse).")
iv_correction = st.selectbox("IV Correction Mode", options=["auto", "none"], index=0, help="'auto' nutzt eine interne Logik zur Anpassung der IV (VRP/Contango-Effekt).")
if iv_correction == "none":
    manual_iv_corr = st.number_input("Manual IV Correction Factor (0.0-1.0)", value=0.0, step=0.05, format="%.2f", help="Manueller Faktor zur Reduzierung der IV (z.B. 0.85 für 15% Reduktion).")
    if manual_iv_corr > 0:
        iv_correction = manual_iv_corr
t_cost = st.number_input("Transaction Cost / Contract", value=TRANSACTION_COST_PER_CONTRACT, step=0.1, help="Fixkosten pro gehandeltem Kontrakt (Kauf + Verkauf).")

# --- Main Area: Strategy Construction ---
st.header("🏗️ Strategy Construction")

# --- Strategy-Level Management ---
with st.container(border=True):
    st.subheader("🛠️ Strategy Management")
    m_col1, m_col2, m_col3 = st.columns(3)
    with m_col1:
        strat_tp = st.number_input("Strategy Take Profit %", value=float(st.session_state.get('mc_take_profit', 50.0)), step=10.0, help="Schließt die gesamte Strategie, wenn der Gewinn diesen Prozentsatz der Prämie erreicht.")
    with m_col2:
        strat_sl = st.number_input("Strategy Stop Loss %", value=float(st.session_state.get('mc_stop_loss', 200.0)), step=10.0, help="Schließt die gesamte Strategie, wenn der Verlust diesen Prozentsatz der Prämie erreicht.")
    with m_col3:
        strat_dc = st.number_input("Strategy DTE Close", value=int(st.session_state.get('mc_dte_close', 21)), step=1, help="Schließt die gesamte Strategie automatisch bei dieser Anzahl an Resttagen.")

# Update actual values from inputs for leg construction
current_price = st.session_state.get('mc_cp_input', current_price)
volatility = st.session_state.get('mc_iv_input', volatility)
dte = st.session_state.get('mc_dte_input', dte)

if 'legs' not in st.session_state:
    st.session_state.legs = [
        {'type': 'Put', 'action': 'Short', 'strike': 95.0, 'premium': 1.50},
        {'type': 'Put', 'action': 'Long', 'strike': 90.0, 'premium': 0.50}
    ]

def add_leg():
    st.session_state.legs.append({'type': 'Put', 'action': 'Short', 'strike': current_price, 'premium': 1.0})

def remove_leg(index):
    st.session_state.legs.pop(index)

for i, leg in enumerate(st.session_state.legs):
    with st.expander(f"Leg {i+1}: {leg['action']} {leg['type']} @ {leg['strike']}", expanded=True):
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            leg['type'] = st.selectbox(f"Type##{i}", options=["Call", "Put"], index=0 if leg['type'] == "Call" else 1)
            leg['action'] = st.selectbox(f"Action##{i}", options=["Long", "Short"], index=0 if leg['action'] == "Long" else 1)
        with col2:
            leg['strike'] = st.number_input(f"Strike##{i}", value=float(leg['strike']), step=1.0, help="Ausübungspreis der Option.")
            leg['premium'] = st.number_input(f"Premium##{i}", value=float(leg['premium']), step=0.05, help="Eingenommene (Short) oder gezahlte (Long) Prämie pro Aktie.")
        with col3:
            st.write("")
            st.write("")
            if st.button(f"Remove Leg##{i}"):
                remove_leg(i)
                st.rerun()

st.button("Add Leg", on_click=add_leg)

# --- Calculation ---
if st.button("🚀 Run Simulation", use_container_width=True):
    options = []
    for leg in st.session_state.legs:
        options.append({
            'strike': leg['strike'],
            'premium': leg['premium'],
            'is_call': leg['type'] == "Call",
            'is_long': leg['action'] == "Long",
            'stop_loss_pct': strat_sl if strat_sl > 0 else None,
            'take_profit_pct': strat_tp if strat_tp > 0 else None,
            'dte_close': strat_dc if strat_dc > 0 else None
        })
    
    with st.spinner("Running Monte Carlo Simulation..."):
        try:
            simulator = UniversalOptionsMonteCarloSimulator(
                current_price=current_price,
                volatility=volatility,
                dte=dte,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
                num_simulations=num_simulations,
                random_seed=seed,
                iv_correction=iv_correction,
                transaction_cost_per_contract=t_cost
            )
            
            results = simulator.analyze_strategy(options)
            
            # --- Display Results ---
            st.header("📊 Analysis Results")
            
            # Key Metrics
            m_col1, m_col2, m_col3, m_col4 = st.columns(4)
            with m_col1:
                st.metric("Expected Value", f"${results['expected_value']:.2f}")
                st.metric("EV (Raw)", f"${results['expected_value_raw']:.2f}")
            with m_col2:
                st.metric("Prob. Profit", f"{results['prob_profit']:.1f}%")
                st.metric("Prob. Loss", f"{results['prob_loss']:.1f}%")
            with m_col3:
                st.metric("Max Profit (Sim)", f"${results['max_profit']:.2f}")
                st.metric("Max Loss (Sim)", f"${results['max_loss']:.2f}")
            with m_col4:
                st.metric("Net Cashflow", f"${results['initial_cashflow']:.2f}")
                st.metric("IV Corr. Factor", f"{results['iv_correction_factor']*100:.1f}%")

            # Management Stats
            if results.get('management_stats'):
                st.subheader("🛡️ Exit Statistics")
                stats = results['management_stats']
                s_col1, s_col2, s_col3, s_col4, s_col5 = st.columns(5)
                with s_col1:
                    st.metric("Take Profit", f"{stats['tp_count']}", f"{(stats['tp_count']/stats['total_sims'])*100:.1f}%")
                with s_col2:
                    st.metric("Stop Loss", f"{stats['sl_count']}", f"{(stats['sl_count']/stats['total_sims'])*100:.1f}%", delta_color="inverse")
                with s_col3:
                    st.metric("DTE Close", f"{stats['dc_count']}", f"{(stats['dc_count']/stats['total_sims'])*100:.1f}%")
                with s_col4:
                    st.metric("Expiration", f"{stats['exp_count']}", f"{(stats['exp_count']/stats['total_sims'])*100:.1f}%")
                with s_col5:
                    st.metric("Other/Planned", f"{stats['pdte_count']}", f"{(stats['pdte_count']/stats['total_sims'])*100:.1f}%")

            # Greeks
            st.subheader("Simulation Greeks")
            greeks = simulator.calculate_greeks(options)
            g_col1, g_col2, g_col3 = st.columns(3)
            with g_col1:
                st.metric("Delta", f"{greeks['delta']:.4f}")
            with g_col2:
                st.metric("Gamma", f"{greeks['gamma']:.4f}")
            with g_col3:
                st.metric("Vega", f"{greeks['vega']:.4f}")

            # Leg Analysis Table
            st.subheader("Leg Details")
            leg_data = []
            for leg in results['leg_analysis']:
                leg_data.append({
                    "Leg": leg['leg_number'],
                    "Position": leg['position'],
                    "Type": leg['type'],
                    "Strike": leg['strike'],
                    "Premium": leg['premium_per_share'],
                    "Cashflow": leg['cashflow']
                })
            st.table(pd.DataFrame(leg_data))

            # Risk & Distribution
            st.subheader("Risk & Distribution")
            p_col1, p_col2 = st.columns(2)
            with p_col1:
                st.write("**Percentiles (Payoff):**")
                st.json(results['percentiles'])
            with p_col2:
                st.write("**Breakeven Points (Underlying):**")
                if results['breakeven_points']:
                    st.write(", ".join([f"${be:.2f}" for be in results['breakeven_points']]))
                else:
                    st.write("None found in simulation range.")

            # --- Payoff Diagram ---
            st.subheader("📈 Payoff Diagram (Simulation)")
            
            # Use final simulated prices for the x-axis and payoffs for the y-axis
            # We sort them to get a clean line
            sim_prices = results.get('simulated_prices')
            sim_payoffs = results.get('total_payoffs')
            
            if sim_prices is not None and sim_payoffs is not None:
                sort_idx = np.argsort(sim_prices)
                sorted_prices = sim_prices[sort_idx]
                sorted_payoffs = sim_payoffs[sort_idx]
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=sorted_prices, y=sorted_payoffs, name="MC Payoff", line=dict(color='royalblue', width=2)))
                
                # Zero line
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                # Current price line
                fig.add_vline(x=current_price, line_dash="dot", line_color="green", annotation_text="Current Price")
                
                fig.update_layout(
                    xaxis_title="Stock Price at Expiry / Exit",
                    yaxis_title="Total Payoff ($)",
                    margin=dict(l=20, r=20, t=20, b=20),
                    hovermode="x unified"
                )
                st.plotly_chart(fig, use_container_width=True)
                
                # --- Price Distribution Histogram ---
                st.subheader("📊 Price Distribution at Exit")
                fig_dist = go.Figure()
                fig_dist.add_trace(go.Histogram(x=sim_prices, nbinsx=100, name="Price Dist", marker_color='lightseagreen'))
                fig_dist.add_vline(x=current_price, line_dash="dot", line_color="red", annotation_text="Start Price")
                fig_dist.update_layout(
                    xaxis_title="Stock Price",
                    yaxis_title="Frequency",
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                st.plotly_chart(fig_dist, use_container_width=True)
            else:
                # If analyze_strategy doesn't return them directly, we might need to modify it or calculate them
                st.info("Simulation price data for plotting not directly available from analyze_strategy results.")

        except Exception as e:
            st.error(f"Error during simulation: {e}")
            logger.exception("Monte Carlo Simulation failed")

st.divider()
st.info("Hinweis: Diese Seite nutzt die `UniversalOptionsMonteCarloSimulator` Klasse direkt aus `src/monte_carlo_simulation.py`.")
