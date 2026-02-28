import logging
import os
import streamlit as st
import pandas as pd
import numpy as np
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.position_insurance_calculation import calculate_position_insurance_metrics, calculate_collar_metrics
from pages.documentation_text.position_insurance_page_doc import get_position_insurance_documentation

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
if 'pi_calls_df' not in st.session_state:
    st.session_state['pi_calls_df'] = None
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
            # 1. Load Data from DB (puts AND calls in one query)
            params = {
                "symbol": symbol_input,
                "today": pd.Timestamp.now().strftime('%Y-%m-%d')
            }
            
            sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'position_insurance.sql'
            all_options_df = select_into_dataframe(sql_file_path=sql_file_path, params=params)
            
            if all_options_df.empty:
                st.warning(f"Keine Optionen für {symbol_input} gefunden (oder Symbol existiert nicht in Datenbasis).")
                st.session_state['pi_df'] = None
                st.session_state['pi_calls_df'] = None
            else:
                # Split into puts and calls
                puts_df = all_options_df[all_options_df['contract_type'] == 'put'].copy()
                calls_df = all_options_df[all_options_df['contract_type'] == 'call'].copy()

                if puts_df.empty:
                    st.warning(f"Keine Put-Optionen für {symbol_input} gefunden.")
                    st.session_state['pi_df'] = None
                    st.session_state['pi_calls_df'] = None
                else:
                    # 2. Verify stock price
                    current_price = puts_df['live_stock_price'].iloc[0]
                    if pd.isna(current_price):
                        current_price = puts_df['stock_close'].iloc[0]
                    
                    # Fill live_stock_price column for calculation if partial/missing
                    puts_df['live_stock_price'] = current_price

                    if pd.isna(current_price):
                        st.error("Kein aktueller Aktienkurs gefunden.")
                        st.session_state['pi_df'] = None
                        st.session_state['pi_calls_df'] = None
                    else:
                        # 3. Calculate Married Put metrics
                        puts_df = calculate_position_insurance_metrics(puts_df, cost_basis_input)
                        
                        # Store in session state
                        st.session_state['pi_df'] = puts_df
                        st.session_state['pi_calls_df'] = calls_df if not calls_df.empty else None
                        st.session_state['pi_symbol'] = symbol_input
                        st.rerun()

        except Exception as e:
            st.error(f"Fehler bei der Berechnung: {e}")
            logger.error(e, exc_info=True)
            st.session_state['pi_df'] = None
            st.session_state['pi_calls_df'] = None

# --- Display Logic (Always runs if data exists) ---
if st.session_state['pi_df'] is not None:
    df = st.session_state['pi_df']
    calls_df = st.session_state.get('pi_calls_df')
    current_price = df['live_stock_price'].iloc[0]
    
    # Recalculate metrics (supports cost basis change without reload)
    df = calculate_position_insurance_metrics(df, cost_basis_input)

    # --- Ensure expiration_date is datetime ---
    df['expiration_date'] = pd.to_datetime(df['expiration_date'])

    # --- Pre-Filter: Only Strike Price >= Cost Basis ---
    df = df[df['strike_price'] >= cost_basis_input].copy()

    if df.empty:
        st.warning(f"Keine Put-Optionen mit Strike >= {cost_basis_input:.2f} gefunden.")
    else:
        # --- Month map for display ---
        month_map = {
            1: 'Januar', 2: 'Februar', 3: 'März', 4: 'April', 5: 'Mai', 6: 'Juni',
            7: 'Juli', 8: 'August', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Dezember'
        }
        
        # --- Put month display columns ---
        df['exp_month_sort'] = df['expiration_date'].apply(lambda x: x.strftime('%Y-%m'))
        df['exp_month_display'] = df['expiration_date'].apply(lambda x: f"{x.strftime('%Y-%m')} ({month_map.get(x.month, '')})")
        
        df['option_label'] = df.apply(
            lambda row: f"{row['symbol']} {row['expiration_date'].year} {row['expiration_date'].strftime('%d-%b').upper()} {row['strike_price']:.2f} PUT ({int(row['days_to_expiration'])})",
            axis=1
        )

        unique_put_months = df[['exp_month_sort', 'exp_month_display']].drop_duplicates().sort_values('exp_month_sort')
        available_put_months_display = unique_put_months['exp_month_display'].tolist()
        
        # --- Prepare Call months (if calls available) ---
        available_call_months_display = []
        if calls_df is not None and not calls_df.empty:
            calls_df = calls_df.copy()
            calls_df['expiration_date'] = pd.to_datetime(calls_df['expiration_date'])
            # Filter calls: strike >= current stock price
            calls_df = calls_df[calls_df['strike_price'] >= current_price].copy()
            if not calls_df.empty:
                calls_df['call_exp_month_sort'] = calls_df['expiration_date'].apply(lambda x: x.strftime('%Y-%m'))
                calls_df['call_exp_month_display'] = calls_df['expiration_date'].apply(lambda x: f"{x.strftime('%Y-%m')} ({month_map.get(x.month, '')})")
                unique_call_months = calls_df[['call_exp_month_sort', 'call_exp_month_display']].drop_duplicates().sort_values('call_exp_month_sort')
                available_call_months_display = unique_call_months['call_exp_month_display'].tolist()

        # =====================================================
        # ROW 1: Month Selection (Buy Put Month + Sell Call Month)
        # =====================================================
        col_put_month, col_call_month = st.columns(2)
        
        with col_put_month:
            selected_put_month_display = st.selectbox(
                "Buy Put Month",
                options=available_put_months_display,
                index=0 if available_put_months_display else None,
                key='put_month_key'
            )
        
        with col_call_month:
            call_month_options = ["None"] + available_call_months_display
            sell_call_month = st.selectbox(
                "Sell Call Month (optional – für Collar)",
                options=call_month_options,
                index=0,
                key='call_month_key'
            )
        
        collar_enabled = (sell_call_month != "None")

        # =====================================================
        # Call Strike Selection (only when Collar enabled)
        # =====================================================
        selected_call_price = None
        selected_call_strike = None

        if collar_enabled and calls_df is not None and not calls_df.empty:
            calls_for_month = calls_df[calls_df['call_exp_month_display'] == sell_call_month].copy()
            
            if calls_for_month.empty:
                st.info("Keine Call-Optionen für diesen Monat verfügbar.")
                collar_enabled = False
            else:
                # Also filter: call strike >= put strike (minimum = cost_basis, since puts are filtered >= cost_basis)
                calls_for_month = calls_for_month.sort_values('strike_price')
                
                call_strike_options = calls_for_month.apply(
                    lambda r: f"{r['strike_price']:.2f} (Prämie: {r['option_price']:.2f}$)",
                    axis=1
                ).tolist()
                
                selected_call_display = st.selectbox(
                    "Call Strike auswählen",
                    options=call_strike_options,
                    key='call_strike_key'
                )
                
                # Parse selected call strike and price
                if selected_call_display:
                    selected_call_idx = call_strike_options.index(selected_call_display)
                    selected_call_row = calls_for_month.iloc[selected_call_idx]
                    selected_call_strike = float(selected_call_row['strike_price'])
                    selected_call_price = float(selected_call_row['option_price'])
        elif collar_enabled:
            st.info("Keine Call-Optionen verfügbar.")
            collar_enabled = False

        # =====================================================
        # ROW 2: Filters (Profit Slider + Call-Strike warning)        
        # =====================================================
        col_filters_1, col_filters_2 = st.columns([1, 1])
        
        with col_filters_1:
            max_profit_pct = df['locked_in_profit_pct'].max()
            if pd.isna(max_profit_pct) or max_profit_pct < 0:
                max_profit_pct = 10.0
            
            min_profit_target = st.slider(
                "Min. Locked-in Profit (%)",
                min_value=0.0,
                max_value=float(max_profit_pct) + 5.0,
                value=0.0,
                step=0.5,
                help="Filtert Optionen, die weniger als diesen Prozentsatz an Gewinn garantieren."
            )
        
        with col_filters_2:
            if collar_enabled and selected_call_strike is not None:
                st.write("")  # spacing
                # Warning if call strike < any put strike in filtered data
                st.caption(f"Gewählter Call: {selected_call_strike:.2f}$ Strike, Prämie {selected_call_price:.2f}$")

        # --- Applying Filters ---
        # 1. Put Month
        if selected_put_month_display:
            display_df = df[df['exp_month_display'] == selected_put_month_display].copy()
            header_month = selected_put_month_display
        else:
            display_df = df.copy()
            header_month = "Alle"

        # 2. Profit Filter
        if min_profit_target > 0:
            display_df = display_df[display_df['locked_in_profit_pct'] >= min_profit_target]

        # --- Calculate Collar Metrics if enabled ---
        if collar_enabled and selected_call_price is not None and selected_call_strike is not None:
            display_df = calculate_collar_metrics(display_df, selected_call_price, selected_call_strike, cost_basis_input)
            
            # Warning: call strike < put strike
            puts_above_call = display_df[display_df['strike_price'] > selected_call_strike]
            if not puts_above_call.empty:
                st.warning(f"⚠️ {len(puts_above_call)} Put(s) haben einen Strike über dem Call-Strike ({selected_call_strike:.2f}$) – kein typischer Collar.")

        # --- Header Stats ---
        st.divider()
        unrealized_pl = current_price - cost_basis_input
        unrealized_pl_pct = (unrealized_pl / cost_basis_input) * 100

        if collar_enabled and selected_call_price is not None:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Aktueller Kurs", f"{current_price:.2f} $")
            m2.metric("Einstandskurs", f"{cost_basis_input:.2f} $")
            m3.metric("Call-Prämie (Einnahme)", f"{selected_call_price:.2f} $")
            net_cost_example = display_df['collar_net_cost'].iloc[0] if not display_df.empty else 0
            m4.metric("Netto-Kosten Collar", f"{net_cost_example:.2f} $",
                      "Credit" if net_cost_example < 0 else "Debit")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Aktueller Kurs", f"{current_price:.2f} $")
            m2.metric("Einstandskurs", f"{cost_basis_input:.2f} $")
            m3.metric("Unrealisierter G/V", f"{unrealized_pl:.2f} $", f"{unrealized_pl_pct:.2f} %")
        
        st.divider()

        # --- Smart Recommendations ---
        best_value_row = None
        if not display_df.empty:
            candidates = display_df[display_df['time_value_per_month'] > 0]
            if not candidates.empty:
                best_value_idx = candidates['time_value_per_month'].idxmin()
                best_value_row = candidates.loc[best_value_idx]
        
        best_protection_row = None
        if not display_df.empty:
            best_protection_idx = display_df['downside_protection_pct'].idxmin()
            best_protection_row = display_df.loc[best_protection_idx]

        if best_value_row is not None:
            st.info(
                f"💡 **Effizienz-Tipp:** {best_value_row['option_label']} kostet nur **{best_value_row['time_value_per_month']:.2f} $/Monat** Zeitwert "
                f"und sichert **{best_value_row['locked_in_profit_pct']:.2f}%** Gewinn."
            )

        if best_protection_row is not None:
            st.info(
                f"🛡️ **Bester Schutz:** {best_protection_row['option_label']} – "
                f"Absicherung ab **{best_protection_row['downside_protection_pct']:.2f}%** "
                f"unter aktuellem Kurs, kostet **{best_protection_row['annualized_cost_pct']:.2f}% p.a.**"
            )

        # --- Column Config ---
        column_config = {
            "option_label": st.column_config.TextColumn("Put (DTE)", width="large"),
            "expiration_date": None,
            "strike_price": None,
            "option_price": st.column_config.NumberColumn("Put Preis", format="%.2f $"),
            "new_cost_basis": st.column_config.NumberColumn("Neuer Einstand", format="%.2f $"),
            "locked_in_profit": st.column_config.NumberColumn("Locked-in Profit ($)", format="%.2f $"),
            "locked_in_profit_pct": st.column_config.NumberColumn("Locked-in Profit (%)", format="%.2f %%"),
            "risk_pct": None,
            "time_value_per_month": st.column_config.NumberColumn("Zeitwert/Monat", format="%.2f $"),
            "insurance_cost_pct": st.column_config.NumberColumn("Versicherung (%)", format="%.2f %%"),
            "downside_protection_pct": st.column_config.NumberColumn("Absicherungstiefe (%)", format="%.2f %%"),
            "annualized_cost": st.column_config.NumberColumn("Kosten p.a. ($)", format="%.2f $"),
            "annualized_cost_pct": st.column_config.NumberColumn("Kosten p.a. (%)", format="%.2f %%"),
            "upside_drag_pct": st.column_config.NumberColumn("Perf.-Drag (%)", format="%.2f %%"),
            "days_to_expiration": None,
            "live_stock_price": None,
            "stock_close": None,
            "greeks_delta": st.column_config.NumberColumn("Delta", format="%.2f"),
            "contract_type": None,
            "symbol": None,
            "open_interest": st.column_config.NumberColumn("Open Interest"),
            "greeks_theta": None,
            "intrinsic_value": None,
            "time_value": None,
            "annualized_cost": None,
            "upside_drag_pct": None,
            "risk_pct": None,
            "exp_month_sort": None,
            "exp_month_display": None,
            # Collar columns
            "collar_new_cost_basis": st.column_config.NumberColumn("Neuer Einstand (Collar)", format="%.2f $"),
            "collar_locked_in_profit": st.column_config.NumberColumn("Locked-in Profit (Collar)", format="%.2f $"),
            "collar_locked_in_profit_pct": st.column_config.NumberColumn("Locked-in Profit % (Collar)", format="%.2f %%"),
            "collar_net_cost": st.column_config.NumberColumn("Netto-Kosten", format="%.2f $"),
            "collar_max_profit": st.column_config.NumberColumn("Max. Gewinn ($)", format="%.2f $"),
            "collar_max_profit_pct": st.column_config.NumberColumn("Max. Gewinn (%)", format="%.2f %%"),
            "pct_assigned": st.column_config.NumberColumn("% Assigned", format="%.2f %%"),
            "pct_assigned_with_put": st.column_config.NumberColumn("% Assigned (mit Put)", format="%.2f %%"),
        }
        
        # --- Dynamic base_cols based on mode ---
        if collar_enabled and 'collar_net_cost' in display_df.columns:
            header_title = f"Collar Analyse (Put: {header_month} / Call: {sell_call_month})"
            base_cols = [
                'option_label',
                'option_price',
                'collar_net_cost',
                'collar_new_cost_basis',
                'collar_locked_in_profit',
                'collar_locked_in_profit_pct',
                'collar_max_profit',
                'collar_max_profit_pct',
                'pct_assigned',
                'time_value_per_month',
                'downside_protection_pct',
            ]
        else:
            header_title = f"Married Put Analyse – {header_month}"
            base_cols = [
                'option_label',
                'option_price',
                'insurance_cost_pct',
                'time_value_per_month',
                'annualized_cost_pct',
                'new_cost_basis',
                'locked_in_profit',
                'locked_in_profit_pct',
                'downside_protection_pct',
            ]

        st.markdown(f"### {header_title} ({len(display_df)} Optionen)")
        
        # Build column list: base_cols + any extra visible columns
        cols_to_show = [c for c in base_cols if c in display_df.columns]
        cols_to_show += [c for c in display_df.columns if c not in cols_to_show and c in column_config and column_config[c] is not None]
        
        display_df_ordered = display_df[cols_to_show].copy()
        
        if 'symbol' not in display_df_ordered.columns:
            display_df_ordered['symbol'] = display_df['symbol']

        page_display_dataframe(display_df_ordered, page='position_insurance', symbol_column='symbol', column_config=column_config)

# --- Documentation (always visible at bottom) ---
with st.expander("📖 Dokumentation – Feldübersicht", expanded=False):
    st.markdown(get_position_insurance_documentation())
