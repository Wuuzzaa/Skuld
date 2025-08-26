import streamlit as st
import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from src.married_put_calculation import get_married_puts, calculate_married_put_kpis
from config import PATH_DATAFRAME_DATA_MERGED_FEATHER


def load_data():
    """Load the merged dataset"""
    try:
        df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None


def apply_filters(df, filters):
    """Apply all active filters to the dataframe"""
    filtered_df = df.copy()
    
    for filter_name, filter_config in filters.items():
        if filter_config['active']:
            column = filter_config['column']
            filter_type = filter_config['type']
            
            if column not in df.columns:
                continue
                
            if filter_type == 'range':
                min_val = filter_config['min']
                max_val = filter_config['max']
                if min_val is not None:
                    filtered_df = filtered_df[filtered_df[column] >= min_val]
                if max_val is not None:
                    filtered_df = filtered_df[filtered_df[column] <= max_val]
            
            elif filter_type == 'greater':
                value = filter_config['value']
                if value is not None:
                    filtered_df = filtered_df[filtered_df[column] > value]
            
            elif filter_type == 'less':
                value = filter_config['value']
                if value is not None:
                    filtered_df = filtered_df[filtered_df[column] < value]
    
    return filtered_df


def create_filter_ui():
    """Create the filter interface similar to the screenshots"""
    st.markdown("### Married Put Screener - Filter Configuration")
    
    # Create tabs for different filter categories
    tab1, tab2, tab3 = st.tabs(["Options", "Technicals", "Fundamentals"])
    
    filters = {}
    
    with tab1:
        st.markdown("#### Options Filters")
        
        # Time Section
        st.markdown("**Time**")
        col1, col2 = st.columns(2)
        
        with col1:
            dte_min = st.number_input("Days to Expiration (Min)", min_value=0, value=0, key="dte_min")
            filters['dte_min'] = {
                'active': dte_min > 0,
                'column': 'dte',
                'type': 'greater',
                'value': dte_min if dte_min > 0 else None
            }
        
        with col2:
            dte_max = st.number_input("Days to Expiration (Max)", min_value=0, value=20, key="dte_max")
            filters['dte_max'] = {
                'active': dte_max > 0,
                'column': 'dte',
                'type': 'less',
                'value': dte_max if dte_max > 0 else None
            }
        
        # Implied Volatility Section
        st.markdown("**Implied Volatility**")
        col1, col2 = st.columns(2)
        
        with col1:
            iv_min = st.number_input("IV (Min)", min_value=0.0, max_value=1000.0, value=0.0, step=0.1, key="iv_min")
            filters['iv_min'] = {
                'active': iv_min > 0,
                'column': 'iv',
                'type': 'greater',
                'value': iv_min if iv_min > 0 else None  # Already in decimal
            }
        
        with col2:
            iv_max = st.number_input("IV (Max)", min_value=0.0, max_value=1000.0, value=50.0, step=0.1, key="iv_max")
            filters['iv_max'] = {
                'active': iv_max < 1000,
                'column': 'iv',
                'type': 'less',
                'value': iv_max if iv_max < 1000 else None
            }
        
        # Greeks Section
        st.markdown("**Greeks**")
        col1, col2 = st.columns(2)
        
        with col1:
            delta_min = st.number_input("Delta (Min)", min_value=-1.0, max_value=1.0, value=-1.0, step=0.1, key="delta_min")
            filters['delta_min'] = {
                'active': delta_min > -1.0,
                'column': 'delta',
                'type': 'greater',
                'value': delta_min
            }
        
        with col2:
            delta_max = st.number_input("Delta (Max)", min_value=-1.0, max_value=1.0, value=0.0, step=0.1, key="delta_max")
            filters['delta_max'] = {
                'active': delta_max < 1.0,
                'column': 'delta',
                'type': 'less',
                'value': delta_max
            }
    
    with tab2:
        st.markdown("#### Technical Indicators")
        
        # RSI
        col1, col2 = st.columns(2)
        with col1:
            rsi_min = st.number_input("RSI (Min)", min_value=0, max_value=100, value=0, key="rsi_min")
            filters['rsi_min'] = {
                'active': rsi_min > 0,
                'column': 'RSI',
                'type': 'greater',
                'value': rsi_min if rsi_min > 0 else None
            }
        
        with col2:
            rsi_max = st.number_input("RSI (Max)", min_value=0, max_value=100, value=100, key="rsi_max")
            filters['rsi_max'] = {
                'active': rsi_max < 100,
                'column': 'RSI',
                'type': 'less',
                'value': rsi_max if rsi_max < 100 else None
            }
        
        # MACD
        macd_threshold = st.number_input("MACD (Greater than)", value=-999.0, step=0.1, key="macd_threshold")
        filters['macd'] = {
            'active': macd_threshold > -999,
            'column': 'MACD.macd',
            'type': 'greater',
            'value': macd_threshold if macd_threshold > -999 else None
        }
    
    with tab3:
        st.markdown("#### Fundamental Filters")
        
        # Market Cap Dropdown (like in the video)
        market_cap_options = {
            "Any": None,
            "Over $100 Billion": 100e9,
            "Over $50 Billion": 50e9,
            "Over $20 Billion": 20e9,
            "Over $10 Billion": 10e9,
            "Over $1 Billion": 1e9,
            "$20 Billion - $100 Billion": {"min": 20e9, "max": 100e9},
            "$1 Billion - $10 Billion": {"min": 1e9, "max": 10e9},
            "$500 Million - $1 Billion": {"min": 500e6, "max": 1e9},
            "Under $1 Billion": {"max": 1e9},
            "Under $500 Million": {"max": 500e6},
            "Under $100 Million": {"max": 100e6}
        }
        
        selected_market_cap = st.selectbox(
            "Market Cap Filter:",
            options=list(market_cap_options.keys()),
            index=0,  # Default to "Any"
            key="market_cap_dropdown"
        )
        
        # Configure the filter based on selection
        market_cap_filter = market_cap_options[selected_market_cap]
        
        if market_cap_filter is None:
            # "Any" selected - no filter
            filters['mcap_min'] = {'active': False, 'column': 'MarketCap', 'type': 'greater', 'value': None}
            filters['mcap_max'] = {'active': False, 'column': 'MarketCap', 'type': 'less', 'value': None}
        elif isinstance(market_cap_filter, dict):
            # Range filter (e.g., "$1 Billion - $10 Billion")
            filters['mcap_min'] = {
                'active': 'min' in market_cap_filter,
                'column': 'MarketCap',
                'type': 'greater',
                'value': market_cap_filter.get('min')
            }
            filters['mcap_max'] = {
                'active': 'max' in market_cap_filter,
                'column': 'MarketCap',
                'type': 'less',
                'value': market_cap_filter.get('max')
            }
        else:
            # Simple "Over X" filter
            filters['mcap_min'] = {
                'active': True,
                'column': 'MarketCap',
                'type': 'greater',
                'value': market_cap_filter
            }
            filters['mcap_max'] = {'active': False, 'column': 'MarketCap', 'type': 'less', 'value': None}
        
        # P/E Ratio
        col1, col2 = st.columns(2)
        with col1:
            pe_min = st.number_input("P/E Ratio (Min)", min_value=0.0, value=0.0, step=1.0, key="pe_min")
            filters['pe_min'] = {
                'active': pe_min > 0,
                'column': 'P/E',
                'type': 'greater',
                'value': pe_min if pe_min > 0 else None
            }
        
        with col2:
            pe_max = st.number_input("P/E Ratio (Max)", min_value=0.0, value=100.0, step=1.0, key="pe_max")
            filters['pe_max'] = {
                'active': pe_max < 100,
                'column': 'P/E',
                'type': 'less',
                'value': pe_max if pe_max < 100 else None
            }
        
        # Dividend Yield
        div_yield_min = st.number_input("Dividend Yield (Min %)", min_value=0.0, max_value=20.0, value=0.0, step=0.5, key="div_yield")
        filters['div_yield'] = {
            'active': div_yield_min > 0,
            'column': 'Div-Yield',
            'type': 'greater',
            'value': div_yield_min / 100 if div_yield_min > 0 else None
        }
    
    return filters


def display_results_with_state(df_filtered):
    """Display the filtered results and calculate married put KPIs with session state management"""
    if df_filtered.empty:
        st.warning("No options match your filter criteria. Please adjust the filters.")
        return
    
    # Show summary statistics
    st.markdown("### Filter Results Summary")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Options", len(df_filtered))
    with col2:
        st.metric("Unique Symbols", df_filtered['symbol'].nunique())
    with col3:
        avg_iv = df_filtered['iv'].mean() * 100 if 'iv' in df_filtered.columns else 0
        st.metric("Avg IV", f"{avg_iv:.1f}%")
    with col4:
        avg_dte = df_filtered['dte'].mean() if 'dte' in df_filtered.columns else 0
        st.metric("Avg DTE", f"{avg_dte:.0f} days")
    
    # Show available expiration dates
    st.markdown("### Married Put Analysis")
    
    # Get unique expiration dates from filtered data
    exp_dates = sorted(df_filtered['expiration_date'].unique())
    
    if len(exp_dates) == 0:
        st.warning("No expiration dates found in filtered data.")
        return
    
    # Let user select expiration date
    col1, col2 = st.columns([2, 3])
    
    with col1:
        # Show expiration date counts
        exp_date_counts = df_filtered['expiration_date'].value_counts().sort_index()
        st.markdown("**Available Expiration Dates:**")
        for exp_date, count in exp_date_counts.items():
            st.write(f"• {exp_date}: {count} options")
    
    with col2:
        # User selection with session state
        selected_exp_date = st.selectbox(
            "Select Expiration Date for Analysis:",
            options=exp_dates,
            index=0,
            help="Choose which expiration date to analyze for married put KPIs",
            key="exp_date_selector"
        )
        
        # Store in session state
        if selected_exp_date != st.session_state.get('selected_exp_date'):
            st.session_state.selected_exp_date = selected_exp_date
            st.session_state.kpi_results = None  # Clear previous results when date changes
        
        # Analysis button
        analyze_clicked = st.button("Calculate Married Put KPIs", type="primary", key="analyze_btn")
    
    # Calculate KPIs only when button is clicked
    if analyze_clicked and selected_exp_date:
        with st.spinner(f"Calculating Married Put KPIs for expiration {selected_exp_date}..."):
            try:
                # Don't convert - work directly with the timestamp format that's in the dataframe
                st.info(f"Analyzing {len(df_filtered[df_filtered['expiration_date'] == selected_exp_date])} options for {selected_exp_date}")
                
                # Filter the data ourselves instead of relying on the function to do it
                exp_filtered = df_filtered[
                    (df_filtered['expiration_date'] == selected_exp_date) & 
                    (df_filtered['option-type'] == 'put')
                ].copy()
                
                if exp_filtered.empty:
                    st.warning(f"No put options found for expiration date {selected_exp_date}")
                    st.session_state.kpi_results = None
                else:
                    st.info(f"Found {len(exp_filtered)} put options for analysis")
                    
                    # Calculate KPIs row by row since the main function has issues
                    kpi_results = []
                    progress_bar = st.progress(0)
                    
                    for i, (idx, row) in enumerate(exp_filtered.iterrows()):
                        try:
                            # Convert expiration_date to YYYYMMDD format for the KPI function
                            row_copy = row.copy()
                            if hasattr(row_copy['expiration_date'], 'strftime'):
                                row_copy['expiration_date'] = int(row_copy['expiration_date'].strftime('%Y%m%d'))
                            
                            kpis = calculate_married_put_kpis(row_copy)
                            row_with_kpis = row.to_dict()  # Use original row for display
                            row_with_kpis.update(kpis)
                            kpi_results.append(row_with_kpis)
                        except Exception as e:
                            st.warning(f"Failed to calculate KPIs for option {idx}: {e}")
                            continue
                        
                        # Update progress
                        progress_bar.progress((i + 1) / len(exp_filtered))
                    
                    progress_bar.empty()
                    
                    if kpi_results:
                        married_puts_df = pd.DataFrame(kpi_results)
                        # Sort by ROI Score if available
                        if 'roi_score' in married_puts_df.columns:
                            married_puts_df = married_puts_df.sort_values('roi_score', ascending=False).reset_index(drop=True)
                        
                        # Store results in session state
                        st.session_state.kpi_results = married_puts_df
                        st.success(f"Successfully calculated KPIs for {len(married_puts_df)} married put combinations")
                    else:
                        st.session_state.kpi_results = None
                        st.warning("No valid married put KPIs could be calculated.")
                        
            except Exception as e:
                st.error(f"Error calculating married put KPIs: {e}")
                st.session_state.kpi_results = None
    
    # Display stored results if available
    if st.session_state.kpi_results is not None and not st.session_state.kpi_results.empty:
        st.markdown("### Married Put KPI Results")
        
        # Display the results table
        st.dataframe(
            st.session_state.kpi_results,
            use_container_width=True,
            hide_index=True
        )
        
        # Download button
        csv = st.session_state.kpi_results.to_csv(index=False)
        st.download_button(
            label="Download Results as CSV",
            data=csv,
            file_name=f"married_put_analysis_{st.session_state.selected_exp_date}.csv",
            mime="text/csv"
        )
    
    # Show preview of filtered data if no KPIs calculated yet
    elif st.session_state.kpi_results is None:
        st.markdown("**Preview of filtered options data:**")
        st.dataframe(
            df_filtered[['symbol', 'expiration_date', 'option-type', 'strike', 'close', 'delta', 'iv', 'dte']].head(10),
            use_container_width=True,
            hide_index=True
        )


def display_results(df_filtered):
    """Legacy function - kept for compatibility but redirects to state-managed version"""
    display_results_with_state(df_filtered)


def main():
    st.set_page_config(
        page_title="Married Put Screener",
        page_icon="🎯",
        layout="wide"
    )
    
    st.title("Married Put Screener")
    st.markdown("Filter options data and analyze married put strategies with custom criteria.")
    
    # Initialize session state
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    if 'filtered_df' not in st.session_state:
        st.session_state.filtered_df = None
    if 'kpi_results' not in st.session_state:
        st.session_state.kpi_results = None
    if 'selected_exp_date' not in st.session_state:
        st.session_state.selected_exp_date = None
    
    # Load data
    df = load_data()
    if df is None:
        return
    
    st.markdown(f"**Dataset loaded:** {len(df):,} options across {df['symbol'].nunique()} symbols")
    
    # Create filter interface
    filters = create_filter_ui()
    
    # Search button
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 1, 3])
    
    with col1:
        search_clicked = st.button("Submit Search", type="primary", use_container_width=True)
    
    with col2:
        clear_clicked = st.button("Clear Filters", use_container_width=True)
    
    if clear_clicked:
        # Clear session state
        st.session_state.search_performed = False
        st.session_state.filtered_df = None
        st.session_state.kpi_results = None
        st.session_state.selected_exp_date = None
        st.rerun()
    
    if search_clicked:
        # Apply filters and store in session state
        with st.spinner("Applying filters..."):
            st.session_state.filtered_df = apply_filters(df, filters)
            st.session_state.search_performed = True
            st.session_state.kpi_results = None  # Clear previous KPI results
        st.rerun()
    
    # Display results if search was performed
    if st.session_state.search_performed and st.session_state.filtered_df is not None:
        display_results_with_state(st.session_state.filtered_df)


if __name__ == "__main__":
    main()
