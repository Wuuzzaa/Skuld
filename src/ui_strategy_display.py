import streamlit as st
import pandas as pd
import logging
import os
from datetime import datetime
from typing import List, Optional
from src.options_utils import OptionLeg, StrategyMetrics

logger = logging.getLogger(os.path.basename(__file__))

def display_strategy_details(
    symbol: str,
    company_name: str,
    legs: List[OptionLeg],
    metrics: StrategyMetrics,
    extra_info: Optional[dict] = None
):
    """
    Displays the details of an options strategy in a standardized way.
    """
    st.markdown(f"### Details für {symbol}")
    
    # 1. Legs Table
    legs_data = []
    for i, leg in enumerate(legs):
        # Format last_updated if it's a timestamp
        updated_str_massive = leg.last_updated_massive
        updated_str_option_data = leg.last_updated_option_data
        updated_str_stock_data = leg.last_updated_stock_data
        if isinstance(updated_str_massive, (pd.Timestamp, datetime)):
            updated_str_massive = updated_str_massive.strftime('%d.%m.%Y %H:%M')      
        elif pd.isna(updated_str_massive):
            updated_str_massive = "N/A"
        if isinstance(updated_str_option_data, (pd.Timestamp, datetime)):
            updated_str_option_data = leg.last_updated_option_data.strftime('%d.%m.%Y %H:%M')
        elif pd.isna(updated_str_option_data):
            updated_str_option_data = "N/A"
        if isinstance(updated_str_stock_data, (pd.Timestamp, datetime)):
            updated_str_stock_data = leg.last_updated_stock_data.strftime('%d.%m.%Y %H:%M')
        elif pd.isna(updated_str_stock_data):
            updated_str_stock_data = "N/A"


        legs_data.append({
            "Leg": f"Leg {i+1}",
            "Type": "Call" if leg.is_call else "Put",
            "Action": "Long" if leg.is_long else "Short",
            "Strike": leg.strike,
            "Price": leg.premium,
            "BS Price": leg.bs_price if leg.bs_price is not None else "—",
            "Delta": leg.delta,
            "IV": leg.iv,
            "Theta": leg.theta,
            "OI": leg.oi,
            "Volume": leg.volume,
            "Exp Move": leg.expected_move,
            "Updated_Massive": updated_str_massive,
            "Updated_OptionData": updated_str_option_data,
            "Updated_StockData": updated_str_stock_data
        })

    details_df = pd.DataFrame(legs_data)

    # Color-code BS Price comparison: green if market > BS (overpriced, good for sellers), red otherwise
    def _highlight_bs(row):
        styles = [''] * len(row)
        bs_idx = details_df.columns.get_loc('BS Price')
        price_idx = details_df.columns.get_loc('Price')
        if row['BS Price'] != '—' and row['BS Price'] is not None and row['Price'] is not None:
            try:
                bs_val = float(row['BS Price'])
                price_val = float(row['Price'])
                if price_val > bs_val:
                    styles[bs_idx] = 'color: #2ecc71'  # green
                else:
                    styles[bs_idx] = 'color: #e74c3c'  # red
            except (ValueError, TypeError):
                pass
        return styles

    styled_df = details_df.style.apply(_highlight_bs, axis=1)
    st.dataframe(styled_df, hide_index=True, use_container_width=True)
    
    # 2. Key Metrics
    st.markdown("#### Kennzahlen & Unternehmensinfos")
    st.write(f"**Unternehmen:** {company_name}")

    col_info1, col_info2, col_info3, col_info4 = st.columns(4)
    with col_info1:
        st.metric("Max Profit", f"${metrics.max_profit:.2f}")
        st.metric("BPR", f"${metrics.bpr:.2f}")
    with col_info2:
        st.metric("Expected Value", f"${metrics.expected_value:.2f}")
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

    # IV Correction info
    iv_corr_display = f"{metrics.iv_correction_factor*100:.1f}%"
    st.write(f"**IV Correction Factor:** {iv_corr_display}")
    
    if extra_info:
        st.write(f"**Sektor:** {extra_info.get('company_sector', 'N/A')} | **Branche:** {extra_info.get('company_industry', 'N/A')}")
        if 'analyst_mean_target' in extra_info and pd.notnull(extra_info['analyst_mean_target']):
            st.write(f"**Analyst Kursziel:** ${extra_info['analyst_mean_target']:.2f} (Aktuell: ${extra_info.get('close', 0):.2f})")

    # 3. External Links
    display_external_links(symbol, extra_info)

def display_external_links(symbol: str, extra_info: Optional[dict] = None):
    """
    Displays external analysis links for a given symbol.
    """
    st.markdown("#### Links")
    link_col1, link_col2, link_col3, link_col4 = st.columns(4)
    with link_col1:
        st.link_button("TradingView", f"https://www.tradingview.com/symbols/{symbol}/", width="stretch")
        st.link_button("Chart", f"https://www.tradingview.com/chart/?symbol={symbol}", width="stretch")
    with link_col2:
        st.link_button("Finviz", f"https://finviz.com/quote.ashx?t={symbol}", width="stretch")
        if extra_info and 'optionstrat_url' in extra_info and extra_info['optionstrat_url']:
            st.link_button("OptionStrat", extra_info['optionstrat_url'], width="stretch")
    with link_col3:
        st.link_button("Seeking Alpha", f"https://seekingalpha.com/symbol/{symbol}", width="stretch")
        if extra_info and 'Claude' in extra_info and extra_info['Claude']:
            st.link_button("Claude AI Analysis", extra_info['Claude'], width="stretch")
    with link_col4:
        st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{symbol}", width="stretch")
