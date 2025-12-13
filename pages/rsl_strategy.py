import streamlit as st
import pandas as pd
from src.rsl_strategy import calculate_rsl_strategy
from datetime import datetime

st.set_page_config(page_title="RSL Strategy", layout="wide")

st.title("RSL Strategy (Relative Strength Levy)")

with st.expander("Strategy Rules & Description", expanded=False):
    st.markdown("""
    **Strategy Overview:**
    This is a directional stock strategy based on Relative Strength (RSL).
    
    **Rules:**
    1.  **Universe:** S&P 500 stocks.
    2.  **Indicator:** RSL = Close Price / 26-Week SMA.
    3.  **Ranking:** Rank all stocks by RSL in descending order.
    4.  **Entry:** Buy the **Top 5** stocks (Equal Weight).
    5.  **Exit:** Sell if a stock falls out of the **Top 25% (Rank > 125)** OR if **RSL < 1**.
    6.  **Rebalance:** Check weekly (e.g., on Mondays).
    7.  **No Stop Loss:** No hard stop loss orders. Exit is based purely on the weekly ranking.
    
    **Notes:**
    - Avoid stocks pending takeover (flat price action).
    - Diversify across at least 3 sectors if possible.
    - Ignore earnings, chart patterns, etc.
    """)

# Sidebar controls
st.sidebar.header("Settings")
force_refresh = st.sidebar.button("Refresh Data (Fetch from Yahoo)")

# Load Data
with st.spinner("Loading data..."):
    df = calculate_rsl_strategy(force_update=force_refresh)

if df.empty:
    st.error("No data available. Please try refreshing.")
else:
    data_date = pd.to_datetime(df['date'].iloc[0]).strftime('%Y-%m-%d')
    st.info(f"Data Date: {data_date} (Weekly Candle Close)")
    
    # Metrics
    top_1_rsl = df.iloc[0]['RSL']
    top_125_rsl = df.iloc[124]['RSL'] if len(df) >= 125 else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Top 1 RSL", f"{top_1_rsl:.4f}")
    col2.metric("Rank 125 RSL (Cutoff)", f"{top_125_rsl:.4f}")
    col3.metric("Total Stocks Analyzed", len(df))

    # Top 5 - Buy Zone
    st.subheader("🟢 Top 5 - Buy Candidates")
    st.markdown("These are the top ranked stocks. If you are starting new, buy these.")
    
    top_5 = df.head(5).copy()
    st.dataframe(
        top_5.style.format({
            'RSL': '{:.4f}', 
            'close': '{:.2f}', 
            'SMA_26': '{:.2f}'
        })
    )
    
    # Top 25% - Hold Zone
    st.subheader("🟡 Top 25% (Rank 1-125) - Hold Zone")
    st.markdown("If you hold a stock, keep it as long as it is in this list (and RSL > 1).")
    
    # Filter for display
    # We show a bit more than 125 to see what's on the edge
    display_count = 135
    df_display = df.head(display_count).copy()
    
    def highlight_rows(row):
        rank = row['Rank']
        rsl = row['RSL']
        
        if rank <= 5:
            return ['background-color: #d4edda'] * len(row) # Greenish
        elif rank <= 125 and rsl >= 1:
            return ['background-color: #fff3cd'] * len(row) # Yellowish
        else:
            return ['background-color: #f8d7da'] * len(row) # Reddish (Sell)

    st.dataframe(
        df_display.style.apply(highlight_rows, axis=1)
        .format({
            'RSL': '{:.4f}', 
            'close': '{:.2f}', 
            'SMA_26': '{:.2f}'
        })
    )
    
    st.markdown("---")
    st.subheader("Full Ranking")
    st.dataframe(df)

