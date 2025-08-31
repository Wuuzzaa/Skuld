"""
Implied Volatility Filter - Simple Options Filtering by IV
"""

import streamlit as st
import pandas as pd
import numpy as np
import sys
import os

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Import the married put KPI backend
from married_put_kpis import calculate_all_married_put_kpis

def get_married_put_kpi_explanations():
    """
    Comprehensive explanations for all Married Put KPI metrics.
    Returns dictionary with column names as keys and detailed explanations as values.
    """
    return {
        "MP_IntrinsicValue": {
            "name": "Total Put Intrinsic Value (100 Contracts)",
            "description": "The immediate exercise value of 100 put contracts",
            "formula": "100 × Max(Strike Price - Current Stock Price, 0)",
            "example": "If stock = $230, strike = $250: 100 × Max($250 - $230, 0) = $2,000",
            "significance": "Represents the total 'in-the-money' value for your 100-put position."
        },
        
        "MP_TimeValue": {
            "name": "Total Put Time Value (100 Contracts)", 
            "description": "The total premium paid for time until expiration across 100 puts",
            "formula": "100 × (Put Premium - Intrinsic Value per Put)",
            "example": "If each put costs $30 and intrinsic = $20: 100 × ($30 - $20) = $1,000 time value",
            "significance": "Total time decay exposure. This amount decays to zero at expiration."
        },
        
        "MP_TotalInvestment": {
            "name": "Total Investment (100 Shares)",
            "description": "Complete capital required for 100-share married put position",
            "formula": "(100 × Stock Price) + (100 × Put Premium)",
            "example": "(100 × $232) + (100 × $44) = $27,600 total investment",
            "significance": "Your total cash requirement for a realistic 100-share position."
        },
        
        "MP_StockInvestment": {
            "name": "Stock Investment (100 Shares)",
            "description": "Capital required to purchase 100 shares",
            "formula": "100 × Stock Price",
            "example": "100 × $232 = $23,200 for stock purchase",
            "significance": "The equity portion of your married put position."
        },
        
        "MP_PutInvestment": {
            "name": "Put Investment (100 Shares)",
            "description": "Capital required to purchase 100 put contracts",
            "formula": "100 × Put Premium",
            "example": "100 × $44 = $4,400 for put protection",
            "significance": "The insurance premium for protecting your 100-share position."
        },
        
        "MP_EstimatedDividends": {
            "name": "Total Expected Dividend Income (100 Shares)",
            "description": "Estimated total dividends from 100 shares during the holding period",
            "formula": "100 × Quarterly Dividend × Number of Payment Periods",
            "example": "If quarterly dividend is $0.78 per share for 4 quarters: 100 × $0.78 × 4 = $312",
            "significance": "Dividends reduce your net risk and improve breakeven. Higher total dividend income offers better economics."
        },
        
        "MP_MaxRisk_Net": {
            "name": "Maximum Risk (100 Shares, After Dividends)",
            "description": "Worst-case loss for 100-share position if stock goes to zero, accounting for dividend income",
            "formula": "(100 × Stock Price) + (100 × Put Premium) - (100 × Strike Price) - Total Expected Dividends",
            "example": "(100 × $230) + (100 × $30) - (100 × $250) - $312 = -$312 (profit!)",
            "significance": "Your true maximum loss potential for a realistic position size. Negative values indicate guaranteed profit."
        },
        
        "MP_RiskPercent_Net": {
            "name": "Risk as % of Total Investment (After Dividends)",
            "description": "Maximum risk expressed as percentage of your total 100-share investment",
            "formula": "(Maximum Risk Net / Total Investment) × 100",
            "example": "($688 / $27,600) × 100 = 2.49%",
            "significance": "Key risk metric for portfolio management. Lower percentages indicate better risk-adjusted positions."
        },
        
        "MP_Breakeven_Net": {
            "name": "Breakeven Stock Price (After Dividends)",
            "description": "Stock price needed at expiration to break even, including dividend benefits",
            "formula": "Stock Price + Put Premium - Expected Dividends",
            "example": "$230 + $30 - $3.12 = $256.88",
            "significance": "Stock must stay above this price for profitability. Lower breakeven prices are better."
        },
        
        "MP_BreakevenUpside_Net": {
            "name": "Required Stock Movement % (After Dividends)",
            "description": "Percentage stock price increase needed to break even",
            "formula": "((Breakeven Price / Current Stock Price) - 1) × 100",
            "example": "(($256.88 / $230) - 1) × 100 = 11.69%",
            "significance": "Lower percentages indicate easier profit targets. Negative values mean immediate profitability."
        },
        
        "MP_DividendRiskReduction": {
            "name": "Dividend Risk Reduction ($)",
            "description": "Dollar amount by which dividends reduce your maximum risk",
            "formula": "Expected Dividends (same as MP_EstimatedDividends)",
            "example": "$3.12 dividend reduces risk by $3.12",
            "significance": "Quantifies the risk-reduction benefit of dividend income. Higher values improve risk-return profile."
        },
        
        "MP_DividendImpactPercent": {
            "name": "Dividend Risk Reduction (%)",
            "description": "Percentage by which dividends reduce your maximum risk",
            "formula": "(Dividend Risk Reduction / Max Risk Gross) × 100",
            "example": "If dividends reduce $10 risk to $6.88: ($3.12/$10) × 100 = 31.2%",
            "significance": "Shows the relative importance of dividends. Higher percentages indicate dividend-dependent strategies."
        }
    }

def create_kpi_tooltip(column_name, explanation_dict):
    """Create a formatted tooltip for a KPI column"""
    if column_name not in explanation_dict:
        return f"📊 {column_name}"
    
    info = explanation_dict[column_name]
    tooltip_text = f"""
**{info['name']}**

{info['description']}

**Formula:** {info['formula']}

**Example:** {info['example']}

**Why it matters:** {info['significance']}
    """
    return tooltip_text.strip()

def display_selected_row_kpis(selected_row):
    """Display detailed KPIs for a selected row in large format"""
    if selected_row is None or selected_row.empty:
        return
    
    row = selected_row.iloc[0]
    
    # Header with option details
    st.markdown("## 🎯 Selected Option Analysis")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Symbol", row.get('symbol', 'N/A'))
    with col2:
        st.metric("Strike Price", f"${row.get('strike', 0):.0f}")
    with col3:
        st.metric("Put Premium", f"${row.get('ask', 0):.2f}")
    with col4:
        exp_date = row.get('expiration_date', 'N/A')
        if pd.notna(exp_date):
            if hasattr(exp_date, 'strftime'):
                exp_date = exp_date.strftime('%Y-%m-%d')
        st.metric("Expiration", str(exp_date))
    
    st.divider()
    
    # Investment Overview for 100-share position
    st.markdown("### 💰 Investment Overview (100 Shares)")
    invest_col1, invest_col2, invest_col3, invest_col4 = st.columns(4)
    
    with invest_col1:
        total_investment = row.get('MP_TotalInvestment', 0)
        st.metric(
            "Total Investment", 
            f"${total_investment:,.0f}",
            help="Total capital required for 100-share married put position"
        )
    
    with invest_col2:
        stock_investment = row.get('MP_StockInvestment', 0)
        st.metric(
            "Stock Investment", 
            f"${stock_investment:,.0f}",
            help="Capital required to purchase 100 shares"
        )
    
    with invest_col3:
        put_investment = row.get('MP_PutInvestment', 0)
        st.metric(
            "Put Investment", 
            f"${put_investment:,.0f}",
            help="Capital required to purchase 100 put contracts"
        )
    
    with invest_col4:
        shares_qty = row.get('MP_SharesQuantity', 100)
        st.metric(
            "Position Size", 
            f"{shares_qty:.0f} shares",
            help="Number of shares in the married put position"
        )
    
    st.divider()
    
    # Risk Analysis - Most Important Metrics for 100-share position
    st.markdown("### 🎯 Risk Analysis (100 Shares)")
    risk_col1, risk_col2, risk_col3 = st.columns(3)
    
    with risk_col1:
        max_risk = row.get('MP_MaxRisk_Net', 0)
        risk_pct = row.get('MP_RiskPercent_Net', 0)
        
        # Color coding for risk levels
        if risk_pct <= 3:
            delta_color = "normal"
            risk_emoji = "🟢"
        elif risk_pct <= 7:
            delta_color = "off"
            risk_emoji = "🟡"
        else:
            delta_color = "inverse"
            risk_emoji = "🔴"
            
        st.metric(
            f"{risk_emoji} Maximum Risk (Net)", 
            f"${max_risk:,.0f}",
            delta=f"{risk_pct:.2f}% of capital",
            delta_color=delta_color,
            help="Worst-case loss for 100-share position if stock goes to zero"
        )
    
    with risk_col2:
        breakeven = row.get('MP_Breakeven_Net', 0)
        current_price = row.get('close', row.get('live_stock_price', 0))
        breakeven_diff = breakeven - current_price if current_price > 0 else 0
        
        st.metric(
            "Breakeven Price", 
            f"${breakeven:.2f}",
            delta=f"${breakeven_diff:.2f} vs current",
            help="Stock price needed at expiration to break even (per share)"
        )
    
    with risk_col3:
        upside_req = row.get('MP_BreakevenUpside_Net', 0)
        upside_color = "normal" if upside_req <= 10 else "off" if upside_req <= 20 else "inverse"
        
        st.metric(
            "Required Stock Move", 
            f"{upside_req:.1f}%",
            delta="upside needed",
            delta_color=upside_color,
            help="Percentage stock price increase needed to break even"
        )
    
    st.divider()
    
    # Dividend Benefits for 100-share position
    st.markdown("### 💎 Dividend Benefits (100 Shares)")
    div_col1, div_col2, div_col3 = st.columns(3)
    
    with div_col1:
        est_dividends = row.get('MP_EstimatedDividends', 0)
        div_payments = row.get('MP_DividendPayments', 0)
        st.metric(
            "Expected Dividends", 
            f"${est_dividends:,.0f}",
            delta=f"{div_payments:.0f} payments" if div_payments > 0 else "during hold period",
            help="Total dividends expected from 100 shares during the holding period"
        )
    
    with div_col2:
        risk_reduction = row.get('MP_DividendRiskReduction', 0)
        st.metric(
            "Risk Reduction ($)", 
            f"${risk_reduction:,.0f}",
            help="Dollar amount by which dividends reduce your maximum risk"
        )
    
    with div_col3:
        impact_pct = row.get('MP_DividendImpactPercent', 0)
        st.metric(
            "Risk Reduction (%)", 
            f"{impact_pct:.1f}%",
            help="Percentage by which dividends reduce your maximum risk"
        )
    
    # Strategy Summary
    st.markdown("### 📊 Strategy Summary")
    
    # Create a simple assessment
    protection_pct = 100 - risk_pct if risk_pct > 0 else 100
    
    summary_col1, summary_col2 = st.columns(2)
    
    with summary_col1:
        st.info(f"""
        **Capital Protection:** {protection_pct:.1f}% of your ${total_investment:.2f} investment is protected
        
        **Risk Profile:** {risk_emoji} {'Low' if risk_pct <= 3 else 'Medium' if risk_pct <= 7 else 'High'} Risk Strategy
        
        **Dividend Boost:** ${est_dividends:.2f} in dividend income reduces risk by {impact_pct:.1f}%
        """)
    
    with summary_col2:
        if upside_req <= 5:
            outlook = "🎯 **Excellent** - Low upside requirement"
        elif upside_req <= 15:
            outlook = "✅ **Good** - Moderate upside requirement"
        elif upside_req <= 25:
            outlook = "⚠️ **Fair** - Higher upside needed"
        else:
            outlook = "❌ **Challenging** - Significant upside required"
            
        st.info(f"""
        **Profit Outlook:** {outlook}
        
        **Breakeven Target:** Stock needs to reach ${breakeven:.2f} (+{upside_req:.1f}%)
        
        **Time Horizon:** Until {exp_date}
        """)


def load_options_data():
    """Load the main options dataframe"""
    try:
        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'merged_df.feather')
        if os.path.exists(data_path):
            df = pd.read_feather(data_path)
            st.success(f"Loaded data: {len(df):,} rows")
            return df
        else:
            st.error("Data file not found")
            return None
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None


def filter_by_iv(df, min_iv, max_iv):
    """Filter dataframe by implied volatility range"""
    if df is None or df.empty:
        return df
    
    # Convert IV to numeric (create a copy to avoid SettingWithCopyWarning)
    df = df.copy()
    df['iv_numeric'] = pd.to_numeric(df['iv'], errors='coerce')
    
    # Filter by IV range
    filtered_df = df[
        (df['iv_numeric'] >= min_iv) & 
        (df['iv_numeric'] <= max_iv) &
        (df['iv_numeric'].notna())
    ]
    
    return filtered_df


def filter_by_dte(df, min_dte, max_dte):
    """Filter dataframe by days to expiration range"""
    if df is None or df.empty:
        return df
    
    # Try different column names for DTE
    dte_col = None
    for col in ['dte', 'DTE', 'days_to_expiration', 'DaysToExpiration']:
        if col in df.columns:
            dte_col = col
            break
    
    if dte_col is None:
        # Calculate DTE if expiration_date exists
        if 'expiration_date' in df.columns:
            df['calculated_dte'] = (pd.to_datetime(df['expiration_date']) - pd.Timestamp.now()).dt.days
            dte_col = 'calculated_dte'
        else:
            return df  # No DTE data available
    
    # Convert DTE to numeric
    df['dte_numeric'] = pd.to_numeric(df[dte_col], errors='coerce')
    
    # Filter by DTE range
    filtered_df = df[
        (df['dte_numeric'] >= min_dte) & 
        (df['dte_numeric'] <= max_dte) &
        (df['dte_numeric'].notna())
    ]
    
    return filtered_df


def filter_by_strike_vs_price(df):
    """Filter to only show options where strike > current live price (OTM puts for married puts)"""
    if df is None or df.empty:
        return df
    
    # Try different column names for current price
    price_col = None
    for col in ['live_stock_price', 'close', 'current_price', 'price']:
        if col in df.columns:
            price_col = col
            break
    
    if price_col is None or 'strike' not in df.columns:
        return df  # No price data available
    
    # Convert to numeric
    df['strike_numeric'] = pd.to_numeric(df['strike'], errors='coerce')
    df['price_numeric'] = pd.to_numeric(df[price_col], errors='coerce')
    
    # Filter: strike > current price (OTM puts)
    filtered_df = df[
        (df['strike_numeric'] > df['price_numeric']) &
        (df['strike_numeric'].notna()) &
        (df['price_numeric'].notna())
    ]
    
    return filtered_df


def filter_puts_only(df):
    """Filter to only show PUT options (for married put strategy)"""
    if df is None or df.empty:
        return df
    
    if 'option-type' not in df.columns:
        return df  # No option type data available
    
    # Filter for puts only - check various put representations
    filtered_df = df[df['option-type'].isin(['put', 'Put', 'PUT', 'P', 'p'])]
    
    return filtered_df


def main():
    st.title("IV & DTE Filter")
    
    # Load data
    df = load_options_data()
    if df is None:
        return
    
    # Simple IV range inputs
    st.subheader("Implied Volatility Filter")
    col1, col2 = st.columns(2)
    with col1:
        min_iv = st.number_input("Min IV (%)", min_value=0.0, max_value=500.0, value=10.0, step=1.0) / 100
    with col2:
        max_iv = st.number_input("Max IV (%)", min_value=0.0, max_value=500.0, value=50.0, step=1.0) / 100
    
    # Simple DTE range inputs
    st.subheader("Days to Expiration Filter")
    col3, col4 = st.columns(2)
    with col3:
        min_dte = st.number_input("Min DTE", min_value=0, max_value=1000, value=7, step=1)
    with col4:
        max_dte = st.number_input("Max DTE", min_value=0, max_value=1000, value=90, step=1)
    
    # Filter and display
    if st.button("Apply Filters & Calculate KPIs"):
        # Apply all filters in sequence
        filtered_df = filter_puts_only(df)                    # Only PUT options
        filtered_df = filter_by_iv(filtered_df, min_iv, max_iv)
        filtered_df = filter_by_dte(filtered_df, min_dte, max_dte)
        filtered_df = filter_by_strike_vs_price(filtered_df)  # Only strikes > current price
        
        if len(filtered_df) > 0:
            st.write(f"Found: {len(filtered_df)} PUT options (Strike > Live Price)")
            
            # Send filtered data to married put backend for KPI calculation
            with st.spinner("Calculating Married Put KPIs..."):
                try:
                    # Calculate all married put KPIs for the filtered data
                    filtered_df_with_kpis = calculate_all_married_put_kpis(filtered_df)
                    
                    st.success(f"KPIs calculated successfully for {len(filtered_df_with_kpis)} options!")
                    
                    # Format display columns for main data
                    display_df = filtered_df_with_kpis.copy()
                    
                    # Format IV column as percentage
                    if 'iv' in display_df.columns:
                        display_df['IV (%)'] = (pd.to_numeric(display_df['iv'], errors='coerce') * 100).round(1)
                        display_df = display_df.drop('iv', axis=1)
                    
                    # Add calculated DTE as display column if it was calculated
                    if 'calculated_dte' in display_df.columns:
                        display_df['DTE'] = display_df['calculated_dte'].round(0).astype(int)
                    
                    # Separate original data from KPIs
                    kpi_columns = [col for col in display_df.columns if any(word in col for word in 
                                 ['MP_', 'Protection', 'Cost', 'Risk', 'Profit', 'Days', 'Efficiency', 'Hedge', 
                                  'Breakeven', 'Upside', 'Time', 'Implied', 'Dividend', 'Margin', 'Annualized'])]
                    
                    # Original data columns (everything except KPIs)
                    original_columns = [col for col in display_df.columns if col not in kpi_columns]
                    
                    # Show original filtered data
                    st.subheader("Filtered Options Data")
                    st.dataframe(display_df[original_columns], use_container_width=True)
                    
                    # Show KPIs in separate table
                    if kpi_columns:
                        st.subheader(f"Married Put KPIs ({len(kpi_columns)} metrics)")
                        
                        # Get KPI explanations
                        kpi_explanations = get_married_put_kpi_explanations()
                        
                        # Create expandable help section
                        with st.expander("📖 KPI Explanations - Click to view detailed descriptions"):
                            st.markdown("### Married Put Strategy KPI Guide")
                            st.markdown("*Click on any metric name below for detailed explanation*")
                            
                            # Group KPIs by category
                            cost_metrics = [col for col in kpi_columns if any(term in col for term in ['Intrinsic', 'Time', 'Outlay', 'Dividend'])]
                            risk_metrics = [col for col in kpi_columns if any(term in col for term in ['Risk', 'MaxRisk'])]
                            breakeven_metrics = [col for col in kpi_columns if any(term in col for term in ['Breakeven', 'Upside'])]
                            impact_metrics = [col for col in kpi_columns if any(term in col for term in ['Impact', 'Reduction'])]
                            
                            if cost_metrics:
                                st.markdown("#### 💰 Cost & Income Metrics")
                                for col in cost_metrics:
                                    if col in kpi_explanations:
                                        info = kpi_explanations[col]
                                        with st.expander(f"❓ {info['name']} ({col})"):
                                            st.markdown(f"**Description:** {info['description']}")
                                            st.markdown(f"**Formula:** `{info['formula']}`")
                                            st.markdown(f"**Example:** {info['example']}")
                                            st.markdown(f"**Significance:** {info['significance']}")
                            
                            if risk_metrics:
                                st.markdown("#### 🎯 Risk Metrics")
                                for col in risk_metrics:
                                    if col in kpi_explanations:
                                        info = kpi_explanations[col]
                                        with st.expander(f"❓ {info['name']} ({col})"):
                                            st.markdown(f"**Description:** {info['description']}")
                                            st.markdown(f"**Formula:** `{info['formula']}`")
                                            st.markdown(f"**Example:** {info['example']}")
                                            st.markdown(f"**Significance:** {info['significance']}")
                            
                            if breakeven_metrics:
                                st.markdown("#### 📈 Breakeven Metrics")
                                for col in breakeven_metrics:
                                    if col in kpi_explanations:
                                        info = kpi_explanations[col]
                                        with st.expander(f"❓ {info['name']} ({col})"):
                                            st.markdown(f"**Description:** {info['description']}")
                                            st.markdown(f"**Formula:** `{info['formula']}`")
                                            st.markdown(f"**Example:** {info['example']}")
                                            st.markdown(f"**Significance:** {info['significance']}")
                            
                            if impact_metrics:
                                st.markdown("#### 📊 Dividend Impact Metrics")
                                for col in impact_metrics:
                                    if col in kpi_explanations:
                                        info = kpi_explanations[col]
                                        with st.expander(f"❓ {info['name']} ({col})"):
                                            st.markdown(f"**Description:** {info['description']}")
                                            st.markdown(f"**Formula:** `{info['formula']}`")
                                            st.markdown(f"**Example:** {info['example']}")
                                            st.markdown(f"**Significance:** {info['significance']}")
                        
                        # Include symbol and strike for identification in KPI table
                        kpi_display_columns = []
                        if 'symbol' in display_df.columns:
                            kpi_display_columns.append('symbol')
                        if 'strike' in display_df.columns:
                            kpi_display_columns.append('strike')
                        if 'expiration_date' in display_df.columns:
                            kpi_display_columns.append('expiration_date')
                        
                        kpi_display_columns.extend(kpi_columns)
                        
                        # Display the KPI table with selection capability
                        st.markdown("### 📊 KPI Values")
                        st.markdown("*Click on a row to see detailed analysis below*")
                        
                        # Use data_editor for selection capability
                        selected_data = st.data_editor(
                            display_df[kpi_display_columns], 
                            use_container_width=True,
                            num_rows="dynamic",
                            disabled=kpi_display_columns,  # Make all columns read-only
                            key="kpi_table"
                        )
                        
                        # Check if user selected a row (streamlit automatically adds selection)
                        if hasattr(st.session_state, 'kpi_table') and 'edited_rows' in st.session_state.kpi_table:
                            edited_rows = st.session_state.kpi_table['edited_rows']
                            if edited_rows:
                                # Get the first edited row index
                                selected_row_idx = list(edited_rows.keys())[0]
                                selected_row = display_df.iloc[selected_row_idx:selected_row_idx+1]
                                
                                st.divider()
                                display_selected_row_kpis(selected_row)
                        
                        # Alternative: Use selectbox for row selection
                        st.markdown("### 🔍 Select Option for Detailed Analysis")
                        
                        # Create option labels for selection
                        option_labels = []
                        for idx, row in display_df.iterrows():
                            symbol = row.get('symbol', 'N/A')
                            strike = row.get('strike', 0)
                            premium = row.get('ask', 0)
                            exp_date = row.get('expiration_date', 'N/A')
                            if pd.notna(exp_date) and hasattr(exp_date, 'strftime'):
                                exp_date = exp_date.strftime('%m/%d')
                            option_labels.append(f"{symbol} ${strike:.0f} PUT @ ${premium:.2f} (exp: {exp_date})")
                        
                        if option_labels:
                            selected_option = st.selectbox(
                                "Choose an option to analyze:",
                                options=range(len(option_labels)),
                                format_func=lambda x: option_labels[x],
                                key="option_selector"
                            )
                            
                            if selected_option is not None:
                                selected_row = display_df.iloc[selected_option:selected_option+1]
                                st.divider()
                                display_selected_row_kpis(selected_row)
                        
                        # Summary statistics
                        st.markdown("### 📈 Quick Insights")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            if 'MP_RiskPercent_Net' in display_df.columns:
                                avg_risk = display_df['MP_RiskPercent_Net'].mean()
                                st.metric("Average Risk %", f"{avg_risk:.2f}%")
                        
                        with col2:
                            if 'MP_EstimatedDividends' in display_df.columns:
                                avg_dividend = display_df['MP_EstimatedDividends'].mean()
                                st.metric("Average Dividends", f"${avg_dividend:.2f}")
                        
                        with col3:
                            if 'MP_BreakevenUpside_Net' in display_df.columns:
                                avg_upside = display_df['MP_BreakevenUpside_Net'].mean()
                                st.metric("Average Required Upside", f"{avg_upside:.1f}%")
                        
                        # Risk categorization
                        if 'MP_RiskPercent_Net' in display_df.columns:
                            st.markdown("### 🚦 Risk Analysis")
                            risk_data = display_df['MP_RiskPercent_Net'].dropna()
                            if not risk_data.empty:
                                low_risk = len(risk_data[risk_data <= 3])
                                medium_risk = len(risk_data[(risk_data > 3) & (risk_data <= 7)])
                                high_risk = len(risk_data[risk_data > 7])
                                
                                risk_col1, risk_col2, risk_col3 = st.columns(3)
                                with risk_col1:
                                    st.metric("🟢 Low Risk (≤3%)", low_risk)
                                with risk_col2:
                                    st.metric("🟡 Medium Risk (3-7%)", medium_risk)
                                with risk_col3:
                                    st.metric("🔴 High Risk (>7%)", high_risk)
                        
                        # Best opportunities highlighting
                        if len(display_df) > 0:
                            st.markdown("### 🏆 Best Opportunities")
                            
                            # Create scoring system
                            score_df = display_df.copy()
                            
                            # Lower risk is better (invert)
                            if 'MP_RiskPercent_Net' in score_df.columns:
                                risk_scores = 10 - (score_df['MP_RiskPercent_Net'] / score_df['MP_RiskPercent_Net'].max() * 10)
                                score_df['risk_score'] = risk_scores.fillna(0)
                            else:
                                score_df['risk_score'] = 5
                            
                            # Higher dividends are better
                            if 'MP_EstimatedDividends' in score_df.columns:
                                div_scores = (score_df['MP_EstimatedDividends'] / score_df['MP_EstimatedDividends'].max() * 10).fillna(0)
                                score_df['dividend_score'] = div_scores
                            else:
                                score_df['dividend_score'] = 5
                            
                            # Lower upside requirement is better (invert)
                            if 'MP_BreakevenUpside_Net' in score_df.columns:
                                upside_scores = 10 - (score_df['MP_BreakevenUpside_Net'] / score_df['MP_BreakevenUpside_Net'].max() * 10)
                                score_df['upside_score'] = upside_scores.fillna(0)
                            else:
                                score_df['upside_score'] = 5
                            
                            # Calculate composite score
                            score_df['composite_score'] = (
                                score_df['risk_score'] * 0.4 + 
                                score_df['dividend_score'] * 0.3 + 
                                score_df['upside_score'] * 0.3
                            )
                            
                            # Show top 3 opportunities
                            top_opportunities = score_df.nlargest(min(3, len(score_df)), 'composite_score')
                            
                            for idx, (_, row) in enumerate(top_opportunities.iterrows(), 1):
                                with st.container():
                                    st.markdown(f"**#{idx} - {row.get('symbol', 'N/A')} ${row.get('strike', 'N/A')} PUT**")
                                    opp_col1, opp_col2, opp_col3, opp_col4 = st.columns(4)
                                    
                                    with opp_col1:
                                        risk_val = row.get('MP_RiskPercent_Net', 0)
                                        st.metric("Risk %", f"{risk_val:.1f}%")
                                    
                                    with opp_col2:
                                        div_val = row.get('MP_EstimatedDividends', 0)
                                        st.metric("Dividends", f"${div_val:.2f}")
                                    
                                    with opp_col3:
                                        upside_val = row.get('MP_BreakevenUpside_Net', 0)
                                        st.metric("Req. Upside", f"{upside_val:.1f}%")
                                    
                                    with opp_col4:
                                        score_val = row.get('composite_score', 0)
                                        st.metric("Score", f"{score_val:.1f}/10")
                                    
                                    st.divider()
                    else:
                        st.warning("No KPI columns found")
                    
                except Exception as e:
                    st.error(f"Error calculating KPIs: {e}")
                    st.write("Showing filtered data without KPIs:")
                    
                    # Fallback: show filtered data without KPIs
                    display_df = filtered_df.copy()
                    if 'iv' in display_df.columns:
                        display_df['IV (%)'] = (pd.to_numeric(display_df['iv'], errors='coerce') * 100).round(1)
                        display_df = display_df.drop('iv', axis=1)
                    
                    if 'calculated_dte' in display_df.columns:
                        display_df['DTE'] = display_df['calculated_dte'].round(0).astype(int)
                    
                    st.dataframe(display_df, use_container_width=True)
        else:
            st.warning("No options found matching the filter criteria")


if __name__ == "__main__":
    main()
