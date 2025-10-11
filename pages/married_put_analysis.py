import streamlit as st
import pandas as pd
import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.database import select_into_dataframe

# Titel
st.subheader("Married Put Analysis")

# SQL Query
married_put_sql = """
SELECT
    *
FROM
    (
        SELECT
            ROW_NUMBER() OVER (
                PARTITION BY
                    symbol
                ORDER BY
                    roi_annualized_pct DESC
            ) as symbol_option_rank,
            *
        FROM
            (
                SELECT
                    *,
                    minimum_potential_profit_total_annualized / total_investment * 100 as roi_annualized_pct
                FROM
                    (
                        SELECT
                            *,
                            (total_investment + minimum_potential_profit) as total_return,
                            minimum_potential_profit / total_investment * 100 as roi_pct,
                            round(
                                (minimum_potential_profit / days_to_expiration) * 365,
                                2
                            ) as minimum_potential_profit_total_annualized
                        FROM
                            (
                                SELECT
                                    *,
                                    (
                                        (
                                            number_of_stocks * (live_stock_price + premium_option_price)
                                        ) + 3.5
                                    ) as total_investment,
                                    round(
                                        dividend_sum_to_expiration - (extrinsic_value * number_of_stocks) -3.5,
                                        2
                                    ) as minimum_potential_profit
                                FROM
                                    (
                                        SELECT
                                            *,
                                            ROUND(extrinsic_value * number_of_stocks + 3.5, 2) as max_loss_total,
                                            CAST(ceil(extrinsic_value / "Current-Div") as Integer) as dividends_to_break_even,
                                            ROUND(dividends_to_expiration * "Current-Div", 2) * number_of_stocks AS dividend_sum_to_expiration
                                        FROM
                                            (
                                                SELECT
                                                    100 as number_of_stocks,
                                                    symbol,
                                                    Company,
                                                    sector,
                                                    Industry,
                                                    expiration_date,
                                                    days_to_expiration,
                                                    option_open_interest,
                                                    bid,
                                                    ask,
                                                    spread_ptc,
                                                    premium_option_price,
                                                    intrinsic_value,
                                                    extrinsic_value,
                                                    strike,
                                                    iv,
                                                    round(impliedVolatility, 2) as impliedVolatility,
                                                    delta,
                                                    SMA200,
                                                    live_stock_price,
                                                    strike_stock_price_difference,
                                                    strike_stock_price_difference_ptc,
                                                    analyst_mean_target as analyst_mean_target_price_year,
                                                    "Fair-Value",
                                                    earnings_date,
                                                    days_to_ernings,
                                                    "No-Years",
                                                    classification,
                                                    "Payouts/-Year",
                                                    "Current-Div",
                                                    CAST(
                                                        ROUND(("Payouts/-Year" * (days_to_expiration / 365.0))) AS INTEGER
                                                    ) AS dividends_to_expiration
                                                FROM
                                                    OptionDataMerged
                                                WHERE
                                                    has_fundamental_data_dividend_radar = true
                                                    and "option-type" = 'puts'
                                                    and strike > live_stock_price * 1.2
                                            )
                                    )
                            )
                    )
                WHERE
                    extrinsic_value > 0
                    and option_open_interest > 0
                    and days_to_expiration > 90
            )
    )
WHERE
    symbol_option_rank <= 3
ORDER BY
    roi_annualized_pct DESC;
"""

# Filter Controls
col1, col2, col3, col4 = st.columns(4)

with col1:
    max_results = st.number_input("Max Results", min_value=10, max_value=1000, value=50, step=10)

with col2:
    min_roi = st.number_input("Min ROI % (annualized)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)

with col3:
    max_roi = st.number_input("Max ROI % (annualized)", min_value=0.0, max_value=100.0, value=7.0, step=1.0)

with col4:
    min_days = st.number_input("Min Days to Expiration", min_value=30, max_value=500, value=90, step=10)

# Auto-load data on page load or when filters change
# Using session state to track if data needs to be reloaded
filter_key = f"{max_results}_{min_roi}_{max_roi}_{min_days}"
if 'last_filter_key' not in st.session_state or st.session_state['last_filter_key'] != filter_key:
    st.session_state['last_filter_key'] = filter_key
    
    with st.spinner("Loading married put analysis..."):
        try:
            # Execute SQL query
            df = select_into_dataframe(married_put_sql)
            
            if df is not None and not df.empty:
                # Apply ROI filters
                df = df[
                    (df['roi_annualized_pct'] >= min_roi) & 
                    (df['roi_annualized_pct'] <= max_roi)
                ]
                
                # Apply days filter
                if min_days != 90:
                    df = df[df['days_to_expiration'] >= min_days]
                
                # Limit results
                df = df.head(max_results)
                
                # Store in session state
                st.session_state['married_put_df'] = df
                
            else:
                st.warning("No data found")
                st.session_state['married_put_df'] = pd.DataFrame()
                
        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.session_state['married_put_df'] = pd.DataFrame()

# Display data if it exists
if 'married_put_df' in st.session_state and not st.session_state['married_put_df'].empty:
    df = st.session_state['married_put_df']
    
    # Symbol filter
    symbols = ['All'] + sorted(df['symbol'].unique().tolist())
    selected_symbol = st.selectbox("Filter by Symbol", symbols)
    
    # Apply symbol filter
    display_df = df if selected_symbol == 'All' else df[df['symbol'] == selected_symbol]
    
    # Key columns for display (removed symbol_option_rank)
    key_columns = [
        'symbol', 'Company', 'expiration_date', 'days_to_expiration',
        'strike', 'live_stock_price', 'premium_option_price', 'extrinsic_value',
        'total_investment', 'minimum_potential_profit', 'roi_pct', 'roi_annualized_pct',
        'delta', 'iv', 'option_open_interest', 'classification', 'Current-Div',
        'dividends_to_expiration', 'dividend_sum_to_expiration'
    ]
    
    # Filter columns that actually exist in the dataframe
    available_columns = [col for col in key_columns if col in display_df.columns]
    
    # Display the dataframe
    st.dataframe(
        display_df[available_columns],
        use_container_width=True,
        column_config={
            "roi_annualized_pct": st.column_config.NumberColumn(
                "ROI % (Annual)",
                format="%.2f%%"
            ),
            "roi_pct": st.column_config.NumberColumn(
                "ROI %",
                format="%.2f%%"
            ),
            "total_investment": st.column_config.NumberColumn(
                "Total Investment",
                format="$%.2f"
            ),
            "minimum_potential_profit": st.column_config.NumberColumn(
                "Min Profit",
                format="$%.2f"
            ),
            "live_stock_price": st.column_config.NumberColumn(
                "Stock Price",
                format="$%.2f"
            ),
            "strike": st.column_config.NumberColumn(
                "Strike",
                format="$%.2f"
            ),
            "premium_option_price": st.column_config.NumberColumn(
                "Option Premium",
                format="$%.2f"
            )
        }
    )

else:
    st.info("No data available")
    
# Info box with strategy explanation
with st.expander("Strategy Information"):
    st.markdown("""
    **Married Put Strategy:**
    - Delta > abs(-0.85): Probability of finishing in the money
    - A put with Delta -0.30 means ~30% chance it will expire in the money
    - Payout ratio < 100% (earnings should cover dividend)  
    - Buy at small implied volatility < 30%
    - Exercise and unbook stocks only at the end
    - If the option still has time value, it makes sense to sell the put separately
    
    **Filters Applied:**
    - Only PUT options
    - Strike > Stock Price * 1.2 (OTM puts)
    - Extrinsic value > 0
    - Option open interest > 0
    - Days to expiration > 90
    - Top 3 options per symbol by ROI
    """)