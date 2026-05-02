import streamlit as st
import pandas as pd
import logging
import os
from typing import List, Optional
from src.options_utils import OptionLeg, StrategyMetrics

logger = logging.getLogger(os.path.basename(__file__))

def display_strategy_details(
    symbol: str,
    company_name: str,
    legs: List[OptionLeg],
    metrics: StrategyMetrics,
    extra_info: Optional[dict] = None,
    context: Optional[dict] = None
):
    """
    Displays the details of an options strategy in a standardized way.
    """
    st.markdown(f"### Details für {symbol}")

    def transfer_to_mc_debug():
        if context:
            st.session_state['mc_transfer_data'] = {
                'underlying_price': context.get('underlying_price', 100.0),
                'volatility': context.get('volatility', 0.3),
                'dte': context.get('dte', 45),
                'take_profit': context.get('take_profit', 0),
                'stop_loss': context.get('stop_loss', 0),
                'dte_close': context.get('dte_close', 0),
                'legs': [
                    {
                        'type': 'Call' if leg.is_call else 'Put',
                        'action': 'Long' if leg.is_long else 'Short',
                        'strike': leg.strike,
                        'premium': leg.premium
                    } for leg in legs
                ]
            }
            st.switch_page("pages/mc_debug.py")

    # 1. Legs Table
    legs_data = []
    for i, leg in enumerate(legs):
        legs_data.append({
            "Leg": f"Leg {i+1}",
            "Type": "Call" if leg.is_call else "Put",
            "Action": "Long" if leg.is_long else "Short",
            "Strike": leg.strike,
            "Price": leg.premium,
            "Delta": f"{leg.delta:.4f}" if leg.delta is not None else "N/A",
            "IV": f"{leg.iv*100:.1f}%" if leg.iv is not None else "N/A",
            "Theta": f"{leg.theta:.4f}" if leg.theta is not None else "N/A",
            "OI": leg.oi if leg.oi is not None else "N/A",
            "Volume": leg.volume if leg.volume is not None else "N/A",
            "Exp Move": f"${leg.expected_move:.2f}" if leg.expected_move is not None else "N/A"
        })
    
    details_df = pd.DataFrame(legs_data)
    st.table(details_df)
    
    # 2. Key Metrics
    st.markdown("#### Kennzahlen & Unternehmensinfos")
    st.write(f"**Unternehmen:** {company_name}")

    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    with col_info1:
        st.metric("Max Profit", f"${metrics.max_profit:.2f}")
        st.metric("BPR", f"${metrics.bpr:.2f}")
    with col_info2:
        st.metric("Expected Value", f"${metrics.expected_value:.2f}")
        if metrics.expected_value_managed != metrics.expected_value:
             st.metric("EV (Managed)", f"${metrics.expected_value_managed:.2f}")
        st.metric("APDI", f"{metrics.apdi:.2f}%")
    with col_info3:
        if extra_info:
            iv_rank = extra_info.get('iv_rank')
            st.metric("IV Rank", f"{iv_rank:.1f}" if pd.notnull(iv_rank) else "N/A")
            iv_percentile = extra_info.get('iv_percentile')
            st.metric("IV Percentile", f"{iv_percentile:.1f}" if pd.notnull(iv_percentile) else "N/A")
    with col_info4:
        # Sell IV (Average) - we can calculate it from legs or pass it
        avg_sell_iv = sum(leg.iv for leg in legs if not leg.is_long) / sum(1 for leg in legs if not leg.is_long) if any(not leg.is_long for leg in legs) else 0
        st.metric("Sell IV (Avg)", f"{avg_sell_iv*100:.1f}%")
        st.metric("Theta", f"{metrics.total_theta:.4f}")

    # Greeks from Simulation
    st.markdown("#### Simulation Greeks")
    col_greeks1, col_greeks2, col_greeks3, col_greeks4 = st.columns(4)
    with col_greeks1:
        st.metric("Delta", f"{metrics.delta:.4f}")
    with col_greeks2:
        st.metric("Gamma", f"{metrics.gamma:.4f}")
    with col_greeks3:
        st.metric("Vega", f"{metrics.vega:.4f}")
    with col_greeks4:
        st.write("") # Empty placeholder

    # IV Correction info
    iv_corr_display = f"{metrics.iv_correction_factor*100:.1f}%"
    st.write(f"**IV Correction Factor:** {iv_corr_display}")
    
    if extra_info:
        st.write(f"**Sektor:** {extra_info.get('company_sector', 'N/A')} | **Branche:** {extra_info.get('company_industry', 'N/A')}")
        if 'analyst_mean_target' in extra_info and pd.notnull(extra_info['analyst_mean_target']):
            st.write(f"**Analyst Kursziel:** ${extra_info['analyst_mean_target']:.2f} (Aktuell: ${extra_info.get('close', 0):.2f})")

    # 3. External Links
    st.markdown("#### Links")
    link_col1, link_col2, link_col3, link_col4 = st.columns(4)
    with link_col1:
        st.link_button("TradingView", f"https://www.tradingview.com/symbols/{symbol}/", use_container_width=True)
        st.link_button("Chart", f"https://www.tradingview.com/chart/?symbol={symbol}", use_container_width=True)
    with link_col2:
        st.link_button("Finviz", f"https://finviz.com/quote.ashx?t={symbol}", use_container_width=True)
        if extra_info and 'optionstrat_url' in extra_info and extra_info['optionstrat_url']:
            st.link_button("OptionStrat", extra_info['optionstrat_url'], use_container_width=True)
    with link_col3:
        st.link_button("Seeking Alpha", f"https://seekingalpha.com/symbol/{symbol}", use_container_width=True)
        if extra_info and 'Claude' in extra_info and extra_info['Claude']:
            st.link_button("Claude AI Analysis", extra_info['Claude'], use_container_width=True)
    with link_col4:
        st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{symbol}", use_container_width=True)
        if context:
            st.button("🔬 Analyze in MC Debug", on_click=transfer_to_mc_debug, use_container_width=True, type="primary")
