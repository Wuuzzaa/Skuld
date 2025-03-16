import time
from datetime import datetime
import streamlit as st
import pandas as pd
from src.custom_logging import log_info
from src.strategy_multi_indicator_score_direction_calculation import calc_multi_indicator_score_direction

# Title
st.subheader("Multi-Indicator Direction")

# Columns for compact input layout
col_rsi_long, col_rsi_short, col_bb = st.columns(3)
col_stoch_long, col_stoch_short, col_vwma = st.columns(3)
col_macd, col_adx, col_min_score = st.columns(3)

def parse_number(value):
    """Attempts to parse a number from the input. Returns None if empty or invalid."""
    try:
        return int(value) if value.strip() else None
    except ValueError:
        return None

# Inputs with value ranges and optional None values
with col_rsi_long:
    RSI_long = st.text_input("RSI Long", "30")
    RSI_long = parse_number(RSI_long)
with col_rsi_short:
    RSI_short = st.text_input("RSI Short", "70")
    RSI_short = parse_number(RSI_short)
with col_bb:
    BB = st.checkbox("Bollinger Bands")

with col_stoch_long:
    Stoch_long = st.text_input("Stochastic Long", "20")
    Stoch_long = parse_number(Stoch_long)
with col_stoch_short:
    Stoch_short = st.text_input("Stochastic Short", "80")
    Stoch_short = parse_number(Stoch_short)
with col_vwma:
    VWMA = st.checkbox("VWMA")

with col_macd:
    MACD = st.checkbox("MACD")
with col_adx:
    ADX = st.text_input("ADX", "25")
    ADX = parse_number(ADX)
with col_min_score:
    min_score = st.text_input("Min. Score", "3")
    min_score = parse_number(min_score)

# Data processing with a loading status indicator
with st.status("Filtering data... Please wait.", expanded=True) as status:
    df = st.session_state["df"][
        [
            "symbol",
            "open",
            "high",
            "low",
            "close",
            "RSI",
            "Stoch.K",
            "ADX",
            "MACD.macd",
            "VWMA",
            "BB.lower",
            "BB.upper"
        ]
    ].drop_duplicates()

    # Apply filtering function
    filtered_df = calc_multi_indicator_score_direction(df, RSI_long, RSI_short, BB, Stoch_long, Stoch_short, VWMA, MACD, ADX, min_score)
    status.update(label="Filtering complete!", state="complete", expanded=True)

# Display the filtered DataFrame
st.dataframe(filtered_df, use_container_width=True)
