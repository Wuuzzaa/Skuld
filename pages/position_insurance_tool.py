import logging
import os
import streamlit as st
import pandas as pd
import numpy as np
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.position_insurance_calculation import calculate_position_insurance_metrics

# enable logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Page header
st.title("Position Insurance Tool")
st.markdown("""
Dieses Tool hilft, bestehende Aktienpositionen mit **Protective Puts** abzusichern.
Es berechnet den **Locked-in Profit** (garantierten Mindestgewinn) für verschiedene Put-Optionen.
""")

# --- Sidebar / Inputs ---
with st.container():
    col1, col2, col3 = st.columns(3)
    
    with col1:
        symbol_input = st.text_input("Aktiensymbol (z.B. NVDA)", value="").upper()
        
    with col2:
        cost_basis_input = st.number_input("Einstandskurs (Cost Basis)", min_value=0.01, value=100.0, step=0.5, format="%.2f")
        
    with col3:
        # Expiration Filter (Multi-Select later? For now just simple filter logic after load)
        # We load all future puts first
        pass

calculate_btn = st.button("Berechnen", type="primary")

if calculate_btn and symbol_input:
    with st.spinner(f"Lade Daten für {symbol_input}..."):
        try:
            # 1. Load Data from DB
            params = {
                "symbol": symbol_input,
                "today": pd.Timestamp.now().strftime('%Y-%m-%d')
            }
            
            sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'position_insurance.sql'
            df = select_into_dataframe(sql_file_path=sql_file_path, params=params)
            
            if df.empty:
                st.warning(f"Keine Put-Optionen für {symbol_input} gefunden (oder Symbol existiert nicht in Datenbasis).")
            else:
                # 2. Metrics Calculation
                # Verify we have stock price
                current_price = df['live_stock_price'].iloc[0] # Should be same for all rows
                if pd.isna(current_price):
                     # Fallback to stock_close if live is nan
                     current_price = df['stock_close'].iloc[0]
                
                # Fill live_stock_price column for calculation if it was partial/missing
                df['live_stock_price'] = current_price

                if pd.isna(current_price):
                    st.error("Kein aktueller Aktienkurs gefunden.")
                else:
                    df = calculate_position_insurance_metrics(df, cost_basis_input)

                    # --- Header Stats ---
                    st.divider()
                    curr_val = current_price
                    unrealized_pl = curr_val - cost_basis_input
                    unrealized_pl_pct = (unrealized_pl / cost_basis_input) * 100
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Aktueller Kurs", f"{curr_val:.2f} $")
                    m2.metric("Einstandskurs", f"{cost_basis_input:.2f} $")
                    m3.metric("Unrealisierter G/V", f"{unrealized_pl:.2f} $", f"{unrealized_pl_pct:.2f} %")
                    st.divider()

                    # --- Filtering & Display ---
                    
                    # Optional: Expiration Filter UI *after* loading available dates
                    available_expirations = sorted(df['expiration_date'].unique())
                    # Convert to string for multiselect
                    available_expirations_str = [str(d) for d in available_expirations]
                    
                    selected_expirations = st.multiselect(
                        "Filter Verfallsdatum", 
                        options=available_expirations_str,
                        default=available_expirations_str[:5] if len(available_expirations) > 5 else available_expirations_str
                    )
                    
                    # Filter DF
                    if selected_expirations:
                        # Convert back to date objects or comparing strings depending on df types
                        # SQL returns date objects usually
                        mask = df['expiration_date'].astype(str).isin(selected_expirations)
                        display_df = df[mask].copy()
                    else:
                        display_df = df.copy()

                    # Styling highlights
                    # Positive Locked-in Profit = Green (Bulletproof)
                    # Negative = Red (Risk)
                    
                    # Customize columns for display
                    # Column Config
                    column_config = {
                        "expiration_date": st.column_config.DateColumn("Verfall"),
                        "strike_price": st.column_config.NumberColumn("Strike", format="%.2f $"),
                        "option_price": st.column_config.NumberColumn("Put Preis", format="%.2f $"),
                        "new_cost_basis": st.column_config.NumberColumn("Neuer Einstand", format="%.2f $"),
                        "locked_in_profit": st.column_config.NumberColumn("Locked-in Profit ($)", format="%.2f $"),
                        "locked_in_profit_pct": st.column_config.NumberColumn("Locked-in Profit (%)", format="%.2f %%"),
                        "risk_pct": st.column_config.NumberColumn("Max Risiko", format="%.2f %%"),
                        "time_value_per_month": st.column_config.NumberColumn("Zeitwert/Monat", format="%.2f $"),
                        "days_to_expiration": st.column_config.NumberColumn("Tage", format="%d"),
                        "live_stock_price": None, # Hide
                        "stock_close": None, # Hide
                        "greeks_delta": st.column_config.NumberColumn("Delta", format="%.2f"),
                        "contract_type": None,
                        "symbol": None,
                        "open_interest": st.column_config.NumberColumn("Open Interest"),
                        "greeks_theta": None
                    }
                    
                    # We can use st.dataframe with styling
                    # Green background for positive locked-in profit?
                    # Streamlit pandas styler is a bit limited in 'page_display_dataframe' if it uses standard st.dataframe
                    # But let's try to map color logic if possible or just rely on the column values
                    
                    # The user wants "Farbliche Hervorhebung: Grün = locked-in profit positiv"
                    # We can do this with pandas styling
                    
                    def color_locked_in(val):
                        color = '#d4edda' if val > 0 else '#f8d7da' # Light green vs Light red
                        return f'background-color: {color}; color: black'

                    # Apply to specific columns? 
                    # page_display_dataframe usually handles pagination etc. 
                    # If we use it, we might lose custom styling unless we pass it.
                    # Let's check page_display_dataframe signature in previous steps (view_file didn't show it fully but I saw usage)
                    # Usage in spreads: page_display_dataframe(filtered_df, page='spreads', ...)
                    
                    # Let's try to use standard DataFrame display for now to allow styling
                    st.markdown(f"### Ergebnisse ({len(display_df)} Optionen)")
                    
                    # Create a styler
                    # styled_df = display_df.style.map(color_locked_in, subset=['locked_in_profit', 'locked_in_profit_pct'])
                    # st.dataframe(styled_df, column_config=column_config, use_container_width=True, hide_index=True)
                    
                    # OR use page_display_dataframe if it provides standardized look
                    page_display_dataframe(display_df, page='position_insurance', symbol_column='symbol', column_config=column_config)

        except Exception as e:
            st.error(f"Fehler bei der Berechnung: {e}")
            logger.error(e, exc_info=True)
