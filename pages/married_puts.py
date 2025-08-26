import streamlit as st
import pandas as pd
from datetime import datetime
from src.married_put_calculation import get_married_puts
from src.util import get_option_expiry_dates
from src.custom_logging import *

# Titel
st.subheader("Married Put Screener")

# Create layout with multiple columns for main parameters
col_expiration, col_delta_min, col_delta_max = st.columns(3)

# Expiration date selection
with col_expiration:
    expiration_dates = [
        datetime.strptime(str(date), "%Y%m%d").strftime("%Y-%m-%d")
        for date in get_option_expiry_dates()
    ]
    expiration_date = st.selectbox("Expiration Date", expiration_dates)

# Delta range selection
with col_delta_min:
    delta_min = st.number_input("Min Delta (absolute)", min_value=0.05, max_value=0.95, value=0.15, step=0.05,
                               help="Minimum delta for put options (absolute value)")

with col_delta_max:
    delta_max = st.number_input("Max Delta (absolute)", min_value=0.05, max_value=0.95, value=0.45, step=0.05,
                               help="Maximum delta for put options (absolute value)")

# Expandable section for fundamental filters
with st.expander("📊 Fundamental Screening Filters", expanded=False):
    st.markdown("**Filter stocks based on fundamental criteria before calculating married puts**")
    
    # Create columns for fundamental filters
    col_valuation, col_quality, col_growth = st.columns(3)
    
    with col_valuation:
        st.markdown("**Valuation Metrics**")
        pe_ratio_max = st.number_input("Max P/E Ratio", min_value=0.0, max_value=100.0, value=None, 
                                      help="Filter out overvalued stocks")
        pb_ratio_max = st.number_input("Max P/B Ratio", min_value=0.0, max_value=20.0, value=None,
                                      help="Price-to-Book ratio filter")
        
    with col_quality:
        st.markdown("**Quality Metrics**") 
        roe_min = st.number_input("Min ROE (%)", min_value=-50.0, max_value=100.0, value=None,
                                 help="Return on Equity minimum")
        debt_equity_max = st.number_input("Max Debt/Equity", min_value=0.0, max_value=10.0, value=None,
                                         help="Maximum debt-to-equity ratio")
        
    with col_growth:
        st.markdown("**Growth & Dividends**")
        dividend_yield_min = st.number_input("Min Dividend Yield (%)", min_value=0.0, max_value=15.0, value=None,
                                           help="Minimum annual dividend yield")
        market_cap_min = st.number_input("Min Market Cap (B)", min_value=0.0, max_value=5000.0, value=None,
                                        help="Minimum market capitalization in billions")

# Expandable section for advanced options
with st.expander("⚙️ Advanced Options", expanded=False):
    col_volume, col_cost, col_protection = st.columns(3)
    
    with col_volume:
        min_volume = st.number_input("Min Daily Volume", min_value=1, max_value=10000, value=10,
                                   help="Minimum daily trading volume")
        
    with col_cost:
        max_protection_cost = st.number_input("Max Protection Cost (%)", min_value=0.5, max_value=20.0, value=10.0,
                                            help="Maximum cost of protection as % of stock price")
        
    with col_protection:
        min_downside_protection = st.number_input("Min Downside Protection (%)", min_value=0.0, max_value=50.0, value=5.0,
                                                help="Minimum downside protection percentage")

# Load fundamentals data if available
@st.cache_data
def load_fundamentals_data():
    try:
        return pd.read_csv('yahooquery_financial.csv', sep=';', decimal=',')
    except FileNotFoundError:
        st.warning("Fundamentals data not found. Running without fundamental filters.")
        return None

fundamentals_df = load_fundamentals_data()

# Prepare filters dictionary
filters = {
    "delta_min": delta_min,
    "delta_max": delta_max,
    "min_volume": min_volume
}

# Add fundamental filters if values are provided
if fundamentals_df is not None:
    if pe_ratio_max is not None:
        filters["trailingPE"] = {"max": pe_ratio_max}
    if pb_ratio_max is not None:
        filters["priceToBook"] = {"max": pb_ratio_max}
    if roe_min is not None:
        filters["returnOnEquity"] = {"min": roe_min / 100}  # Convert percentage to decimal
    if debt_equity_max is not None:
        filters["debtToEquity"] = {"max": debt_equity_max}
    if dividend_yield_min is not None:
        filters["dividendYield"] = {"min": dividend_yield_min / 100}  # Convert percentage to decimal
    if market_cap_min is not None:
        filters["marketCap"] = {"min": market_cap_min * 1e9}  # Convert billions to actual value

# Calculate married puts with loading indicator
with st.status("Calculating married put opportunities... Please wait.", expanded=True) as status:
    married_puts_df = get_married_puts(
        st.session_state['df'], 
        expiration_date, 
        fundamentals_df=fundamentals_df,
        filters=filters
    )
    status.update(label="Calculation complete!", state="complete", expanded=True)

# Apply post-calculation filters
if not married_puts_df.empty:
    # Filter by protection cost
    married_puts_df = married_puts_df[married_puts_df["protection_cost_pct"] <= max_protection_cost]
    
    # Filter by downside protection
    married_puts_df = married_puts_df[married_puts_df["downside_protection_pct"] >= min_downside_protection]

# Display results
if married_puts_df.empty:
    st.warning("No married put opportunities found with current filters. Try adjusting the criteria.")
else:
    # Summary metrics
    st.markdown("### 📈 Summary")
    col_count, col_avg_cost, col_avg_protection, col_avg_dte = st.columns(4)
    
    with col_count:
        st.metric("Opportunities Found", len(married_puts_df))
    
    with col_avg_cost:
        avg_cost = married_puts_df["protection_cost_pct"].mean()
        st.metric("Avg Protection Cost", f"{avg_cost:.2f}%")
    
    with col_avg_protection:
        avg_protection = married_puts_df["downside_protection_pct"].mean()
        st.metric("Avg Downside Protection", f"{avg_protection:.2f}%")
        
    with col_avg_dte:
        avg_dte = married_puts_df["days_to_expiration"].mean()
        st.metric("Avg Days to Expiration", f"{avg_dte:.0f}")

    # Additional filters for display
    st.markdown("### 🔍 Filter Results")
    col_symbol_filter, col_sort_by = st.columns(2)
    
    with col_symbol_filter:
        unique_symbols = sorted(married_puts_df['symbol'].unique())
        symbol_filter = st.selectbox("Filter by Symbol", ["All Symbols"] + unique_symbols)
    
    with col_sort_by:
        sort_options = {
            "Protection Cost (Low to High)": "protection_cost_pct",
            "Protection Cost (High to Low)": "protection_cost_pct_desc",
            "Downside Protection (High to Low)": "downside_protection_pct_desc", 
            "Max Loss (Low to High)": "max_loss_pct",
            "Days to Expiration": "days_to_expiration",
            "Symbol": "symbol"
        }
        sort_by = st.selectbox("Sort by", list(sort_options.keys()))

    # Apply symbol filter
    display_df = married_puts_df.copy()
    if symbol_filter != "All Symbols":
        display_df = display_df[display_df['symbol'] == symbol_filter]

    # Apply sorting
    sort_column = sort_options[sort_by]
    if sort_column.endswith("_desc"):
        actual_column = sort_column.replace("_desc", "")
        display_df = display_df.sort_values(actual_column, ascending=False)
    else:
        display_df = display_df.sort_values(sort_column, ascending=True)

    # Format numeric columns for better display
    if not display_df.empty:
        display_df_formatted = display_df.copy()
        
        # Format percentage columns
        percentage_cols = ["protection_cost_pct", "downside_protection_pct", "max_loss_pct", "daily_decay_pct"]
        for col in percentage_cols:
            if col in display_df_formatted.columns:
                display_df_formatted[col] = display_df_formatted[col].apply(lambda x: f"{x:.2f}%" if pd.notna(x) else "")
        
        # Format price columns
        price_cols = ["close", "strike", "breakeven_price", "bid", "ask", "max_loss"]
        for col in price_cols:
            if col in display_df_formatted.columns:
                display_df_formatted[col] = display_df_formatted[col].apply(lambda x: f"${x:.2f}" if pd.notna(x) else "")
        
        # Format delta columns
        delta_cols = ["delta", "abs_delta"]
        for col in delta_cols:
            if col in display_df_formatted.columns:
                display_df_formatted[col] = display_df_formatted[col].apply(lambda x: f"{x:.3f}" if pd.notna(x) else "")
        
        # Format IV
        if "iv" in display_df_formatted.columns:
            display_df_formatted["iv"] = display_df_formatted["iv"].apply(lambda x: f"{x:.1f}%" if pd.notna(x) else "")

    # Display the dataframe
    st.markdown("### 📋 Married Put Opportunities")
    log_info(f"Married puts calculated for: {expiration_date}, {len(display_df)} opportunities found")
    
    if not display_df.empty:
        st.dataframe(display_df_formatted, use_container_width=True)
        
        # Download option
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name=f"married_puts_{expiration_date}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime='text/csv'
        )
    else:
        st.info("No results match the current filters.")

# Information section
with st.expander("ℹ️ About Married Put Strategy", expanded=False):
    st.markdown("""
    **Married Put Strategy Overview:**
    
    A married put involves buying a stock and simultaneously purchasing a put option for the same stock. 
    This strategy provides downside protection while maintaining upside potential.
    
    **Key Metrics Explained:**
    - **Protection Cost**: Premium paid for the put as % of stock price
    - **Breakeven Price**: Stock price needed to break even (stock price + put premium)
    - **Downside Protection**: Maximum stock decline protected against
    - **Max Loss**: Maximum possible loss if stock falls below put strike
    - **Daily Decay**: How much the put premium decreases per day (theta)
    
    **Ideal Characteristics:**
    - Low protection cost (< 5-10% of stock price)
    - Reasonable downside protection (> 10-15%)
    - Quality underlying stock (good fundamentals)
    - Sufficient time to expiration (> 30 days)
    """)
