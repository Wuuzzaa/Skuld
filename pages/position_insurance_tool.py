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
    
    # --- Filtering & Display ---
    
    # 1. Generate Helper Columns for Display & Filtering
    # Month Year for Grouping (e.g. "2026-02")
    df['exp_month'] = df['expiration_date'].apply(lambda x: x.strftime('%Y-%m'))
    
    # Formatted Option Label: "NVDA 2026 18-FEB 120.00 PUT (42)"
    # Note: x.strftime('%d-%b').upper() gives "18-FEB"
    df['option_label'] = df.apply(
        lambda row: f"{row['symbol']} {row['expiration_date'].year} {row['expiration_date'].strftime('%d-%b').upper()} {row['strike_price']:.2f} PUT ({int(row['days_to_expiration'])})",
        axis=1
    )

    available_months = sorted(df['exp_month'].unique())
    
    col_filter, _ = st.columns([1, 2])
    with col_filter:
        # Month Filter
        # Default: Select first available month (nearest term) to avoid overwhelming list, or all? 
        # User said: "Buy Put Month" -> Dropdown. Single Select or Multi?
        # "Select a call month as well as a put month from the boxes below" -> Suggests Dropdown (Single Select)
        # Let's offer a Selectbox for Month.
        selected_month = st.selectbox(
            "Verfallsmonat auswählen",
            options=available_months,
            index=0 if available_months else None
        )
    
    # Filter DF by Month
    if selected_month:
        display_df = df[df['exp_month'] == selected_month].copy()
    else:
        display_df = df.copy()

    # Column Config
    column_config = {
        "option_label": st.column_config.TextColumn("Put (DTE)", width="large"),
        "expiration_date": None, # Hiding original date as it is in label
        "strike_price": None, # Hiding strike as it is in label
        "option_price": st.column_config.NumberColumn("Put Preis", format="%.2f $"),
        "new_cost_basis": st.column_config.NumberColumn("Neuer Einstand", format="%.2f $"),
        "locked_in_profit": st.column_config.NumberColumn("Locked-in Profit ($)", format="%.2f $"),
        "locked_in_profit_pct": st.column_config.NumberColumn("Locked-in Profit (%)", format="%.2f %%"),
        "risk_pct": st.column_config.NumberColumn("Max Risiko", format="%.2f %%"),
        "time_value_per_month": st.column_config.NumberColumn("Zeitwert/Monat", format="%.2f $"),
        "days_to_expiration": None, # In label
        "live_stock_price": None, # Hide
        "stock_close": None, # Hide
        "greeks_delta": st.column_config.NumberColumn("Delta", format="%.2f"),
        "contract_type": None,
        "symbol": None,
        "open_interest": st.column_config.NumberColumn("Open Interest"),
        "greeks_theta": None,
        "intrinsic_value": None,
        "time_value": None,
        "exp_month": None # Helper
    }
    
    st.markdown(f"### Ergebnisse für {selected_month} ({len(display_df)} Optionen)")
    
    # Reorder columns to put option_label first
    # We need to construct a robust column list.
    base_cols = ['option_label', 'option_price', 'time_value_per_month', 'new_cost_basis', 'locked_in_profit', 'locked_in_profit_pct']
    # Add others to end if they exist
    cols_to_show = base_cols + [c for c in display_df.columns if c not in base_cols and c in column_config and column_config[c] is not None]
    
    # Filter columns for display
    # page_display_dataframe takes the whole DF and uses config to hide/show. 
    # But to enforce order, we might need to pass a subset DF.
    # However, page_display_dataframe adds 'TradingView' etc links. 
    # Let's just rely on config hiding and hope for decent default order or select columns explicitly.
    display_df_ordered = display_df[cols_to_show].copy() # This enforces order!
    
    # We must ensure 'symbol' is present for the links generation in page_display_dataframe
    if 'symbol' not in display_df_ordered.columns:
        display_df_ordered['symbol'] = display_df['symbol']

    page_display_dataframe(display_df_ordered, page='position_insurance', symbol_column='symbol', column_config=column_config)
