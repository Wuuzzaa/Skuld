import streamlit as st
import pandas as pd
import sys
import os

from config import PATH_DATABASE_QUERY_FOLDER
from src.page_display_dataframe import page_display_dataframe
from src.documentation_renderer import render_married_put_analysis_documentation

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.database import select_into_dataframe

# Titel
st.subheader("Married Put Analysis")

# Filter Controls
col1, col2, col3, col4 = st.columns(4)

with col1:
    max_results = st.number_input("Max Results", min_value=10, max_value=1000, value=50, step=10)

with col2:
    min_roi = st.number_input("Min ROI %", min_value=0.0, max_value=100.0, value=3.0, step=1.0)

with col3:
    max_roi = st.number_input("Max ROI %", min_value=0.0, max_value=100.0, value=7.0, step=1.0)

with col4:
    days_range = st.slider("Days to Expiration", min_value=30, max_value=720, value=(30, 500), step=30)

# Row 2 for Status Filter (Checkboxes)
st.write("---")
st.caption("Dividend Growth Status")

def _on_click_alle():
    """Callback – runs BEFORE next rerun, so widget keys can still be set."""
    st.session_state["chk_contender"] = False
    st.session_state["chk_challenger"] = False
    st.session_state["chk_champion"] = False
    st.session_state["chk_show_all"] = True

cb_cols = st.columns([1, 1, 1, 0.8])

with cb_cols[0]:
    chk_contender = st.checkbox("Contender", value=True, key="chk_contender")
with cb_cols[1]:
    chk_challenger = st.checkbox("Challenger", value=True, key="chk_challenger")
with cb_cols[2]:
    chk_champion = st.checkbox("Champion", value=True, key="chk_champion")
with cb_cols[3]:
    st.button("Alle (kein Filter)", key="btn_select_all", on_click=_on_click_alle)

# "Alle" means no classification filter at all
show_all = st.session_state.get("chk_show_all", False)

# If any individual checkbox is toggled, deactivate "show all"
if any([chk_contender, chk_challenger, chk_champion]):
    show_all = False
    st.session_state["chk_show_all"] = False

# Build selected statuses list from checkboxes
selected_statuses = []
if not show_all:
    if chk_contender:
        selected_statuses.append("Dividend Contender")
    if chk_challenger:
        selected_statuses.append("Dividend Challenger")
    if chk_champion:
        selected_statuses.append("Dividend Champion")

# Auto-load data on page load or when filters change
# Using session state to track if data needs to be reloaded
filter_key = f"{max_results}_{min_roi}_{max_roi}_{days_range}_{selected_statuses}_{show_all}"
if 'last_filter_key' not in st.session_state or st.session_state['last_filter_key'] != filter_key:
    st.session_state['last_filter_key'] = filter_key
    
    with st.spinner("Loading married put analysis..."):
        try:
            # Execute SQL query
            sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'married_put.sql'
            df = select_into_dataframe(sql_file_path=sql_file_path)
            
            if df is not None and not df.empty:
                # Apply ROI filters
                df = df[
                    (df['roi_annualized_pct'] >= min_roi) & 
                    (df['roi_annualized_pct'] <= max_roi)
                ]
                
                # Apply days filter
                df = df[
                    (df['days_to_expiration'] >= days_range[0]) & 
                    (df['days_to_expiration'] <= days_range[1])
                ]

                # Apply Status Filter (skip if "Alle" is active)
                if not show_all and selected_statuses:
                     # 'Classification' is the column name in the DF (aliased from dividend_classification)
                    df = df[df['Classification'].isin(selected_statuses)]
                
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
    
    # All columns for display (matching SQL query output)
    key_columns = [
        'symbol', 'Company', 'Sector', 'Industry',
        'expiration_date', 'days_to_expiration',
        'strike_price', 'live_stock_price', 'premium_option_price',
        'intrinsic_value', 'extrinsic_value',
        'total_investment', 'minimum_potential_profit',
        'roi_pct', 'roi_annualized_pct',
        'max_loss_total', 'total_return',
        'delta', 'impliedVolatility', 'open_interest',
        'Classification', 'No-Years', 'Current-Div',
        'Payouts/-Year', 'dividends_to_expiration', 'dividend_sum_to_expiration',
        'dividends_to_break_even',
        'earnings_date', 'days_to_earnings',
        'analyst_mean_target_price_year',
        'spread_ptc',
        'strike_stock_price_difference', 'strike_stock_price_difference_ptc',
    ]
    
    # Filter columns that actually exist in the dataframe
    available_columns = [col for col in key_columns if col in display_df.columns]

    # show final dataframe with row selection for documentation
    event = st.dataframe(
        display_df[available_columns],
        use_container_width=True,
        height=min(800, 40 + 35 * len(display_df)),
        selection_mode="single-row",
        on_select="rerun",
        key="married_put_table",
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
            "max_loss_total": st.column_config.NumberColumn(
                "Max Loss",
                format="$%.2f"
            ),
            "total_return": st.column_config.NumberColumn(
                "Total Return",
                format="$%.2f"
            ),
            "live_stock_price": st.column_config.NumberColumn(
                "Stock Price",
                format="$%.2f"
            ),
            "strike_price": st.column_config.NumberColumn(
                "Strike",
                format="$%.2f"
            ),
            "premium_option_price": st.column_config.NumberColumn(
                "Option Premium",
                format="$%.2f"
            ),
            "intrinsic_value": st.column_config.NumberColumn(
                "Intrinsic Value",
                format="$%.2f"
            ),
            "extrinsic_value": st.column_config.NumberColumn(
                "Extrinsic Value",
                format="$%.2f"
            ),
            "impliedVolatility": st.column_config.NumberColumn(
                "IV",
                format="%.2f"
            ),
            "spread_ptc": st.column_config.NumberColumn(
                "Spread %",
                format="%.2f%%"
            ),
            "strike_stock_price_difference": st.column_config.NumberColumn(
                "Strike-Stock Diff",
                format="$%.2f"
            ),
            "strike_stock_price_difference_ptc": st.column_config.NumberColumn(
                "Strike-Stock Diff %",
                format="%.2f%%"
            ),
            "dividend_sum_to_expiration": st.column_config.NumberColumn(
                "Div Sum to Exp",
                format="$%.2f"
            ),
            "analyst_mean_target_price_year": st.column_config.NumberColumn(
                "Analyst Target",
                format="$%.2f"
            ),
            "Classification": st.column_config.TextColumn(
                "Dividend Status"
            ),
        }
    )

    # ── Inline Documentation on row click ──────────────────────────
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows and not display_df.empty:
        selected_idx = selected_rows[0]
        selected_row = display_df.iloc[selected_idx]

        st.divider()
        doc_md = render_married_put_analysis_documentation(row=selected_row)
        st.markdown(doc_md)
    else:
        st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die vollständige Berechnung für diese Option zu sehen.")

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
    - Days to expiration > User Selection (Range)
    - Dividend Status matching selection
    - Top 3 options per symbol by ROI
    """)