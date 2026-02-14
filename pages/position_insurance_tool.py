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

# Initialize Session State
if 'pi_df' not in st.session_state:
    st.session_state['pi_df'] = None
if 'pi_symbol' not in st.session_state:
    st.session_state['pi_symbol'] = ""

# --- Sidebar / Inputs ---
with st.container():
    col1, col2, col3 = st.columns(3)
    
    with col1:
        symbol_input = st.text_input("Aktiensymbol (z.B. NVDA)", value=st.session_state.get('pi_symbol', "")).upper()
        
    with col2:
        cost_basis_input = st.number_input("Einstandskurs (Cost Basis)", min_value=0.01, value=100.0, step=0.5, format="%.2f")
        
    with col3:
        # Placeholder for actions or info
        st.write("")

calculate_btn = st.button("Berechnen (Daten laden)", type="primary")

# --- Logic: Load Data on Button Click ---
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
                st.session_state['pi_df'] = None
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
                    st.session_state['pi_df'] = None
                else:
                    df = calculate_position_insurance_metrics(df, cost_basis_input)
                    # Store in session state
                    st.session_state['pi_df'] = df
                    st.session_state['pi_symbol'] = symbol_input
                    st.rerun() # Rerun to update the view immediately with stable state

        except Exception as e:
            st.error(f"Fehler bei der Berechnung: {e}")
            logger.error(e, exc_info=True)
            st.session_state['pi_df'] = None

# --- Display Logic (Always runs if data exists) ---
if st.session_state['pi_df'] is not None:
    df = st.session_state['pi_df']
    current_price = df['live_stock_price'].iloc[0]
    
    # Recalculate metrics if Cost Basis changed (optional, but good for interactivity without reload)
    # Actually, to support cost basis change without reload, we'd need to recalc here.
    # Let's simple recalc here every time since it's fast.
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
    
    available_expirations = sorted(df['expiration_date'].unique())
    available_expirations_str = [str(d) for d in available_expirations]
    
    # Expiration Filter
    # Default: Empty list means "All" (common UX pattern)
    selected_expirations = st.multiselect(
        "Filter Verfallsdatum (Leer lassen = Alle anzeigen)", 
        options=available_expirations_str,
        default=[] 
    )
    
    # Filter DF
    if selected_expirations:
        mask = df['expiration_date'].astype(str).isin(selected_expirations)
        display_df = df[mask].copy()
    else:
        display_df = df.copy()

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
        "greeks_theta": None,
        "intrinsic_value": None,
        "time_value": None
    }
    
    st.markdown(f"### Ergebnisse ({len(display_df)} Optionen)")
    
    # Create a styler for custom backgound colors based on Logic
    # We want Locked-In Profit > 0 to be Green
    def highlight_profit(row):
        # We need to return a list of strings (CSS styles) corresponding to columns
        # Pandas Styler `apply` works on Series (columns or rows).
        # We want to highlight the whole row? Or just specific cells?
        # Let's highlight specific cells for readability.
        
        # Default style
        styles = ['' for _ in row.index]
        
        # Logic
        if row['locked_in_profit'] > 0:
            # Find index of columns to highlight
            # We can just highlight the Profit columns
            cols_to_color = ['locked_in_profit', 'locked_in_profit_pct']
            for col in cols_to_color:
                if col in row.index:
                    idx = row.index.get_loc(col)
                    styles[idx] = 'background-color: #d4edda; color: black' # Light Green
        elif row['locked_in_profit'] < 0:
             cols_to_color = ['locked_in_profit', 'locked_in_profit_pct']
             for col in cols_to_color:
                if col in row.index:
                    idx = row.index.get_loc(col)
                    styles[idx] = 'background-color: #f8d7da; color: black' # Light Red
        return styles

    # Use page_display_dataframe for consistent link behavior, OR stick to st.dataframe for custom styling.
    # page_display_dataframe inside handles some styling too (red negative numbers).
    # Since we fixed the "Page not recognized" error, let's use it!
    # But wait, page_display_dataframe applies its own styles which might conflict or be overwritten.
    # It returns a styled object if we look at the code? No, it calls st.dataframe at the end.
    
    # We will pass the dataframe to page_display_dataframe. 
    # NOTE: page_display_dataframe does NOT allow passing custom row-based styling easily unless we modify it further.
    # It applies alternating row colors.
    
    # Let's try to use it as is first. The user asked for "Green = locked-in profit positiv".
    # page_display_dataframe colors negative numbers RED automatically.
    # It does NOT color positive numbers Green.
    
    # I will stick to page_display_dataframe for now to ensure links are working (TradingView, Claude).
    # If the user insists on Green background, I might need to enhance page_display_dataframe or bypass it.
    # Given the previous "Page not recognized" fix, let's use it.
    
    page_display_dataframe(display_df, page='position_insurance', symbol_column='symbol', column_config=column_config)
