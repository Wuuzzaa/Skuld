"""
Married Put Strategy - Streamlit Dashboard
=========================================

This page displays the complete married put KPIs analysis
calculated using the modular functions from married_put_kpis_new.py
"""

import streamlit as st
import pandas as pd
import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

# Import our KPI calculation functions
from src.married_put_kpis_new import load_option_data, calculate_all_married_put_kpis

# Page configuration
st.set_page_config(
    page_title="Married Put Strategy Analysis",
    page_icon="🛡️",
    layout="wide"
)

def load_married_put_data(shares=200):
    """
    Load and calculate all married put KPIs using the modular functions.
    
    Args:
        shares: Number of shares for the strategy
        
    Returns:
        DataFrame with all calculated KPIs
    """
    try:
        # Load option data from database
        option_data = load_option_data()
        
        if option_data.empty:
            st.error("No option data found in database")
            return pd.DataFrame()
        
        # Calculate all KPIs
        result_data = calculate_all_married_put_kpis(option_data, shares=shares)
        
        return result_data
        
    except Exception as e:
        st.error(f"Error loading married put data: {e}")
        return pd.DataFrame()

def main():
    """Main Streamlit application"""
    
    # Header
    st.title("🛡️ Married Put Strategy Analysis")
    st.markdown("Complete KPI analysis for married put options strategies")
    
    # Strategy explanation and KPI guide
    with st.expander("📖 **Married Put Strategy Guide & KPI Interpretation**", expanded=False):
        st.markdown("""
        ## 🎯 **What is a Married Put Strategy?**
        
        A **Married Put** strategy involves buying stocks and simultaneously purchasing put options to protect against downside risk. 
        It's like buying insurance for your stock position.
        
        ---
        
        ## 📊 **Key Performance Indicators (KPIs) & Target Values**
        
        ### 🔴 **CRITICAL KPIs - Focus on These First:**
        
        | KPI | Good Value | Interpretation |
        |-----|------------|----------------|
        | **Floor %** | **85-95%** | Protection level - higher is better. Shows at what % of current price your protection kicks in |
        | **Max Loss %** | **< 10%** | Maximum possible loss as % of investment - lower is better |
        | **Extrinsic %** | **< 3%** | Time value cost as % of stock price - lower is better |
        | **Total Investment** | **Within Budget** | Total capital required (stock + put premium) |
        
        ### 🟡 **IMPORTANT KPIs - Secondary Analysis:**
        
        | KPI | Good Value | Interpretation |
        |-----|------------|----------------|
        | **Annual Cost** | **< 5%** | Yearly protection cost as % - lower is better |
        | **Monthly Cost** | **< 0.5%** | Monthly protection cost as % - for budgeting |
        | **Breakeven Uplift** | **< 5%** | Stock must rise this % to break even - lower is better |
        | **Dividend Adjusted Breakeven** | **Negative** | Breakeven after dividends - negative means dividends cover costs |
        
        ### 🟢 **ANALYTICAL KPIs - For Deep Analysis:**
        
        | KPI | Purpose | Interpretation |
        |-----|---------|----------------|
        | **Intrinsic Value** | Current protection value | Higher for ITM puts |
        | **Max Loss Abs** | Absolute $ loss limit | Your maximum risk in dollars |
        | **Net Cashflow Ratio** | Strategy efficiency | Income vs total investment |
        | **Dividend Sum** | Income during protection | Quarterly dividend income |
        
        ### 🆕 **ADVANCED CAPITAL EFFICIENCY KPIs - For Professional Analysis:**
        
        | KPI | Good Value | Interpretation |
        |-----|------------|----------------|
        | **Capital-at-Risk per Time** | **< 5,000/year** | Annual risk exposure - lower is better for conservative strategies |
        | **Capital Efficiency Score** | **> 15** | Safety per cost unit - higher means better value. Formula: Floor % ÷ Annual Cost % |
        | **Break-Even Time** | **< 3 years** | Years until dividends cover put costs - shorter is better for income strategies |
        | **Dividend Coverage Ratio** | **> 0.5** | How well dividends cover put costs over option period. >1.0 = fully covered |
        
        ---
        
        ## ⭐ **Quick Selection Tips:**
        
        ### 🎯 **Conservative Protection (Recommended)**
        - **Floor %:** 90-95% (strikes close to current price)
        - **Max Loss %:** < 5%
        - **Extrinsic %:** < 2%
        - **Capital Efficiency Score:** > 20
        - **Break-Even Time:** < 2 years
        
        ### ⚖️ **Balanced Protection**
        - **Floor %:** 80-90%
        - **Max Loss %:** 5-10%
        - **Extrinsic %:** 2-4%
        - **Capital Efficiency Score:** > 15
        - **Break-Even Time:** < 4 years
        
        ### 🎲 **Cost-Conscious Protection**
        - **Floor %:** 70-80%
        - **Max Loss %:** 10-15%
        - **Extrinsic %:** < 5%
        - **Capital Efficiency Score:** > 10
        - **Dividend Coverage Ratio:** > 0.3
        
        ### 💰 **Income-Focused Strategy**
        - **Dividend Coverage Ratio:** > 0.8
        - **Break-Even Time:** < 2 years
        - **Net Cashflow Ratio:** > 0.03
        - **Capital-at-Risk per Time:** < 3,000/year
        
        ---
        
        ## 🚨 **Red Flags - Avoid These:**
        - **Floor % < 70%** → Insufficient protection
        - **Max Loss % > 20%** → Too much risk
        - **Extrinsic % > 8%** → Overpriced options
        - **Annual Cost > 15%** → Too expensive for long-term
        - **Capital Efficiency Score < 5** → Poor value proposition
        - **Break-Even Time > 10 years** → Dividends won't help significantly
        - **Dividend Coverage Ratio < 0.1** → Almost no dividend support
        
        ---
        
        ## 📚 **Advanced KPI Explanations:**
        
        ### 🔄 **Capital-at-Risk per Time**
        **Purpose:** Shows your annualized risk exposure
        - **Formula:** Max Loss Abs ÷ Time to Expiration (years)
        - **Example:** $1,000 max loss over 6 months = $2,000/year capital at risk
        - **Use Case:** Compare strategies with different time horizons
        
        ### ⚡ **Capital Efficiency Score**
        **Purpose:** Measures protection value per insurance cost
        - **Formula:** Floor % ÷ Annual Cost %
        - **Example:** 85% floor with 5% annual cost = Score of 17
        - **Interpretation:** Higher scores = better bang for your buck
        
        ### ⏰ **Break-Even Time**
        **Purpose:** Time until dividends offset put costs
        - **Formula:** Put Price per Share ÷ Annual Dividend per Share
        - **Example:** $2 put cost, $1 annual dividend = 2 years break-even
        - **Strategy:** Look for < 3 years for dividend-focused approaches
        
        ### 🏦 **Dividend Coverage Ratio**
        **Purpose:** How much dividends help with insurance costs
        - **Formula:** (Total Dividends over Option Period) ÷ Put Cost per Share
        - **Example:** $1.50 total dividends, $2 put cost = 0.75 ratio (75% covered)
        - **Target:** >0.5 for meaningful dividend support, >1.0 for full coverage
        """)
    
    # Sidebar configuration
    st.sidebar.header("Strategy Configuration")
    shares = st.sidebar.number_input(
        "Number of Shares", 
        min_value=100, 
        max_value=1000, 
        value=200, 
        step=100,
        help="Number of shares to buy for the married put strategy (each put contract covers 100 shares)"
    )
    
    # Load data button
    if st.sidebar.button("🔄 Load Data", type="primary"):
        st.session_state.data_loaded = True
    
    # Auto-load data on first visit
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = True
    
    if st.session_state.data_loaded:
        with st.spinner("Loading option data and calculating KPIs..."):
            data = load_married_put_data(shares=shares)
        
        if not data.empty:
            # Display summary statistics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Options", len(data))
            
            with col2:
                st.metric("Symbols", data['symbol'].nunique())
            
            with col3:
                avg_total_investment = data['MP_TotalInvestment'].mean()
                st.metric("Avg Total Investment", f"${avg_total_investment:,.0f}")
            
            with col4:
                avg_max_loss_pct = data['MP_MaxLossPercentage'].mean() * 100
                st.metric("Avg Max Loss %", f"{avg_max_loss_pct:.2f}%")
            
            st.divider()
            
            # Data display options
            st.subheader("📊 Complete KPI Analysis")
            
            # Filter options
            col1, col2 = st.columns(2)
            
            with col1:
                symbols = ['All'] + sorted(data['symbol'].unique().tolist())
                selected_symbol = st.selectbox("Filter by Symbol", symbols)
            
            with col2:
                min_strike = float(data['strike'].min())
                max_strike = float(data['strike'].max())
                strike_range = st.slider(
                    "Strike Price Range",
                    min_value=min_strike,
                    max_value=max_strike,
                    value=(min_strike, max_strike)
                )
            
            # Apply filters
            filtered_data = data.copy()
            
            if selected_symbol != 'All':
                filtered_data = filtered_data[filtered_data['symbol'] == selected_symbol]
            
            filtered_data = filtered_data[
                (filtered_data['strike'] >= strike_range[0]) & 
                (filtered_data['strike'] <= strike_range[1])
            ]
            
            # Display tabs for different KPI groups
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                "🏷️ Basic Info", 
                "📈 Basic KPIs", 
                "💰 Cost Analysis", 
                "📊 Dividend Analysis",
                "🔬 Advanced KPIs",  # NEW TAB
                "🔍 Complete Data"
            ])
            
            with tab1:
                st.subheader("Basic Option Information")
                basic_cols = ['symbol', 'strike', 'option_type', 'expiration_date', 'close', 'theoPrice', 'bid', 'ask']
                st.dataframe(
                    filtered_data[basic_cols],
                    use_container_width=True,
                    hide_index=True
                )
            
            with tab2:
                st.subheader("Basic KPIs")
                basic_kpi_cols = [
                    'symbol', 'strike', 'MP_IntrinsicValue', 'MP_ExtrinsicValue', 
                    'MP_ExtrinsicPercentage', 'MP_BreakevenUplift', 'MP_FloorPercentage'
                ]
                st.dataframe(
                    filtered_data[basic_kpi_cols],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "MP_ExtrinsicPercentage": st.column_config.NumberColumn(
                            "Extrinsic %",
                            format="%.2f%%"
                        ),
                        "MP_BreakevenUplift": st.column_config.NumberColumn(
                            "Breakeven Uplift %",
                            format="%.2f%%"
                        ),
                        "MP_FloorPercentage": st.column_config.NumberColumn(
                            "Floor %",
                            format="%.2f%%",
                            help="Protection level - higher values mean better protection"
                        )
                    }
                )
            
            with tab3:
                st.subheader("Cost Analysis")
                cost_cols = [
                    'symbol', 'strike', 'MP_AnnualCost', 'MP_MonthlyCost', 
                    'MP_TotalInvestment', 'MP_MaxLossAbs', 'MP_MaxLossPercentage'
                ]
                st.dataframe(
                    filtered_data[cost_cols],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "MP_TotalInvestment": st.column_config.NumberColumn(
                            "Total Investment",
                            format="$%.2f"
                        ),
                        "MP_MaxLossAbs": st.column_config.NumberColumn(
                            "Max Loss Abs",
                            format="$%.2f"
                        ),
                        "MP_MaxLossPercentage": st.column_config.NumberColumn(
                            "Max Loss %",
                            format="%.2f%%"
                        )
                    }
                )
            
            with tab4:
                st.subheader("Dividend-Adjusted Analysis")
                dividend_cols = [
                    'symbol', 'strike', 'MP_DividendSumToExpiry', 
                    'MP_DividendAdjustedBreakeven', 'MP_NetCashflowRatio'
                ]
                st.dataframe(
                    filtered_data[dividend_cols],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "MP_DividendSumToExpiry": st.column_config.NumberColumn(
                            "Dividend Sum",
                            format="$%.2f"
                        ),
                        "MP_NetCashflowRatio": st.column_config.NumberColumn(
                            "Net Cashflow Ratio",
                            format="%.4f"
                        )
                    }
                )
            
            with tab5:  # NEW TAB for Advanced KPIs
                st.subheader("Advanced Capital Efficiency KPIs")
                st.markdown("*Professional-level KPIs for sophisticated strategy analysis*")
                
                advanced_cols = [
                    'symbol', 'strike', 'MP_CapitalAtRiskPerTime', 'MP_CapitalEfficiencyScore',
                    'MP_BreakEvenTime', 'MP_DividendCoverageRatio'
                ]
                
                # Check if the new columns exist (in case they haven't been calculated yet)
                available_advanced_cols = [col for col in advanced_cols if col in filtered_data.columns]
                
                if len(available_advanced_cols) > 2:  # symbol and strike + at least one KPI
                    st.dataframe(
                        filtered_data[available_advanced_cols],
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "MP_CapitalAtRiskPerTime": st.column_config.NumberColumn(
                                "Capital-at-Risk/Year",
                                format="$%.0f",
                                help="Annual risk exposure - lower is better"
                            ),
                            "MP_CapitalEfficiencyScore": st.column_config.NumberColumn(
                                "Capital Efficiency Score",
                                format="%.2f",
                                help="Protection value per cost unit - higher is better (target >15)"
                            ),
                            "MP_BreakEvenTime": st.column_config.NumberColumn(
                                "Break-Even Time (Years)",
                                format="%.2f",
                                help="Years until dividends offset put costs - shorter is better"
                            ),
                            "MP_DividendCoverageRatio": st.column_config.NumberColumn(
                                "Dividend Coverage Ratio",
                                format="%.3f",
                                help="How well dividends cover put costs (>1.0 = fully covered)"
                            )
                        }
                    )
                    
                    # Add interpretation help
                    with st.expander("📊 How to Interpret Advanced KPIs"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.markdown("""
                            **🔄 Capital-at-Risk per Time:**
                            - < $3,000/year: **Excellent** (low risk)
                            - $3,000-$5,000/year: **Good**
                            - $5,000-$10,000/year: **Moderate**
                            - > $10,000/year: **High Risk**
                            
                            **⚡ Capital Efficiency Score:**
                            - > 20: **Excellent** value
                            - 15-20: **Good** value
                            - 10-15: **Fair** value
                            - < 10: **Poor** value
                            """)
                        
                        with col2:
                            st.markdown("""
                            **⏰ Break-Even Time:**
                            - < 2 years: **Excellent** for income strategies
                            - 2-4 years: **Good**
                            - 4-8 years: **Fair**
                            - > 8 years: **Poor** dividend support
                            
                            **🏦 Dividend Coverage Ratio:**
                            - > 1.0: **Excellent** (fully covered)
                            - 0.5-1.0: **Good** (substantial support)
                            - 0.2-0.5: **Fair** (some support)
                            - < 0.2: **Poor** (minimal support)
                            """)
                
                else:
                    st.warning("Advanced KPIs not yet calculated. These require the updated calculation functions.")
            
            with tab6:  # Complete Data tab (was tab5, now tab6)
                st.subheader("Complete Dataset")
                st.markdown(f"**Showing {len(filtered_data)} of {len(data)} total options**")
                
                # Show all columns with proper formatting
                column_config = {
                    "MP_ExtrinsicPercentage": st.column_config.NumberColumn("Extrinsic %", format="%.2f%%"),
                    "MP_TimeValueRatio": st.column_config.NumberColumn("Time Value Ratio %", format="%.2f%%"),
                    "MP_BreakevenUplift": st.column_config.NumberColumn("Breakeven Uplift %", format="%.2f%%"),
                    "MP_FloorPercentage": st.column_config.NumberColumn("Floor %", format="%.2f%%"),
                    "MP_TotalInvestment": st.column_config.NumberColumn("Total Investment", format="$%.2f"),
                    "MP_MaxLossAbs": st.column_config.NumberColumn("Max Loss Abs", format="$%.2f"),
                    "MP_MaxLossPercentage": st.column_config.NumberColumn("Max Loss %", format="%.2f%%"),
                    "MP_DividendSumToExpiry": st.column_config.NumberColumn("Dividend Sum", format="$%.2f"),
                    "MP_NetCashflowRatio": st.column_config.NumberColumn("Net Cashflow Ratio", format="%.4f"),
                    # Advanced KPI formatting
                    "MP_CapitalAtRiskPerTime": st.column_config.NumberColumn("Capital-at-Risk/Year", format="$%.0f"),
                    "MP_CapitalEfficiencyScore": st.column_config.NumberColumn("Capital Efficiency Score", format="%.2f"),
                    "MP_BreakEvenTime": st.column_config.NumberColumn("Break-Even Time (Years)", format="%.2f"),
                    "MP_DividendCoverageRatio": st.column_config.NumberColumn("Dividend Coverage Ratio", format="%.3f")
                }
                
                st.dataframe(
                    filtered_data,
                    use_container_width=True,
                    hide_index=True,
                    column_config=column_config
                )
                
                # Download option
                csv = filtered_data.to_csv(index=False)
                st.download_button(
                    label="📥 Download Data as CSV",
                    data=csv,
                    file_name=f"married_put_analysis_{shares}_shares.csv",
                    mime="text/csv"
                )
        
        else:
            st.warning("No data available. Please check the database connection.")
    
    else:
        st.info("Click 'Load Data' in the sidebar to start the analysis.")

if __name__ == "__main__":
    main()
