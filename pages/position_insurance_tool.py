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

# ── Page Title ──────────────────────────────────────────────────────
st.title("Position Insurance Tool")

# ── Session State ───────────────────────────────────────────────────
for key, default in [("pi_df", None), ("pi_calls_df", None), ("pi_symbol", "")]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Input Row ───────────────────────────────────────────────────────
c_sym, c_cb, c_btn = st.columns([2, 2, 1])
with c_sym:
    symbol_input = st.text_input(
        "Stock Symbol", value=st.session_state.get("pi_symbol", "")
    ).upper()
with c_cb:
    cost_basis_input = st.number_input(
        "Cost Basis/Shr", min_value=0.01, value=100.0, step=0.5, format="%.2f"
    )
with c_btn:
    st.write("")  # vertical spacing to align button
    calculate_btn = st.button("CALCULATE", type="primary", use_container_width=True)

# ── Load Data on Button Click ──────────────────────────────────────
if calculate_btn and symbol_input:
    with st.spinner(f"Lade Daten für {symbol_input}..."):
        try:
            params = {
                "symbol": symbol_input,
                "today": pd.Timestamp.now().strftime('%Y-%m-%d'),
            }
            sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'position_insurance.sql'
            all_options_df = select_into_dataframe(sql_file_path=sql_file_path, params=params)

            if all_options_df.empty:
                st.warning(f"Keine Optionen für {symbol_input} gefunden.")
                st.session_state['pi_df'] = None
                st.session_state['pi_calls_df'] = None
            else:
                puts_df = all_options_df[all_options_df['contract_type'] == 'put'].copy()
                calls_df = all_options_df[all_options_df['contract_type'] == 'call'].copy()

                if puts_df.empty:
                    st.warning(f"Keine Put-Optionen für {symbol_input} gefunden.")
                    st.session_state['pi_df'] = None
                    st.session_state['pi_calls_df'] = None
                else:
                    current_price = puts_df['live_stock_price'].iloc[0]
                    if pd.isna(current_price):
                        current_price = puts_df['stock_close'].iloc[0]
                    puts_df['live_stock_price'] = current_price

                    if pd.isna(current_price):
                        st.error("Kein aktueller Aktienkurs gefunden.")
                        st.session_state['pi_df'] = None
                        st.session_state['pi_calls_df'] = None
                    else:
                        puts_df = calculate_position_insurance_metrics(puts_df, cost_basis_input)
                        st.session_state['pi_df'] = puts_df
                        st.session_state['pi_calls_df'] = calls_df if not calls_df.empty else None
                        st.session_state['pi_symbol'] = symbol_input
                        st.rerun()
        except Exception as e:
            st.error(f"Fehler bei der Berechnung: {e}")
            logger.error(e, exc_info=True)
            st.session_state['pi_df'] = None
            st.session_state['pi_calls_df'] = None

# =====================================================================
# DISPLAY  (runs whenever session state has data)
# =====================================================================
if st.session_state['pi_df'] is not None:
    df = st.session_state['pi_df']
    calls_df = st.session_state.get('pi_calls_df')
    current_price = df['live_stock_price'].iloc[0]

    # Re-calc (supports cost-basis change without reload)
    df = calculate_position_insurance_metrics(df, cost_basis_input)
    df['expiration_date'] = pd.to_datetime(df['expiration_date'])
    df = df[df['strike_price'] >= cost_basis_input].copy()

    if df.empty:
        st.warning(f"Keine Put-Optionen mit Strike ≥ {cost_basis_input:.2f} gefunden.")
    else:
        # ── Info Banner ─────────────────────────────────────────────
        unrealized_pl = current_price - cost_basis_input
        unrealized_pl_pct = (unrealized_pl / cost_basis_input) * 100
        st.success(
            f"**{st.session_state['pi_symbol']}** – "
            f"Current Price: **{current_price:.2f}$** &ensp;|&ensp; "
            f"Your Current Profit: **{unrealized_pl:+.2f}$ ({unrealized_pl_pct:+.1f}%)**"
        )

        # ── Month & label helpers ───────────────────────────────────
        month_map = {
            1: 'Januar', 2: 'Februar', 3: 'März', 4: 'April', 5: 'Mai', 6: 'Juni',
            7: 'Juli', 8: 'August', 9: 'September', 10: 'Oktober', 11: 'November', 12: 'Dezember',
        }
        df['exp_month_sort'] = df['expiration_date'].apply(lambda x: x.strftime('%Y-%m'))
        df['exp_month_display'] = df['expiration_date'].apply(
            lambda x: f"{x.strftime('%Y-%m')} ({month_map.get(x.month, '')})"
        )
        df['option_label'] = df.apply(
            lambda r: (
                f"{r['symbol']} {r['expiration_date'].year} "
                f"{r['expiration_date'].strftime('%d-%b').upper()} "
                f"{r['strike_price']:.2f} PUT ({int(r['days_to_expiration'])})"
            ), axis=1,
        )

        unique_put_months = (
            df[['exp_month_sort', 'exp_month_display']]
            .drop_duplicates()
            .sort_values('exp_month_sort')
        )
        available_put_months = unique_put_months['exp_month_display'].tolist()

        # Prepare call months
        available_call_months = []
        if calls_df is not None and not calls_df.empty:
            calls_df = calls_df.copy()
            calls_df['expiration_date'] = pd.to_datetime(calls_df['expiration_date'])
            calls_df = calls_df[calls_df['strike_price'] >= current_price].copy()
            if not calls_df.empty:
                calls_df['call_exp_month_sort'] = calls_df['expiration_date'].apply(lambda x: x.strftime('%Y-%m'))
                calls_df['call_exp_month_display'] = calls_df['expiration_date'].apply(
                    lambda x: f"{x.strftime('%Y-%m')} ({month_map.get(x.month, '')})"
                )
                unique_call_months = (
                    calls_df[['call_exp_month_sort', 'call_exp_month_display']]
                    .drop_duplicates()
                    .sort_values('call_exp_month_sort')
                )
                available_call_months = unique_call_months['call_exp_month_display'].tolist()

        # ── Controls: Put Month | Call Month | Call Strike ──────────
        c_pm, c_cm, c_cs = st.columns([2, 2, 3])

        with c_pm:
            selected_put_month = st.selectbox(
                "Buy Put Month",
                options=available_put_months,
                index=0 if available_put_months else None,
                key='put_month_key',
            )

        with c_cm:
            call_opts = ["None"] + available_call_months
            sell_call_month = st.selectbox(
                "Sell Call Month",
                options=call_opts,
                index=0,
                key='call_month_key',
            )

        collar_enabled = sell_call_month != "None"
        selected_call_price = None
        selected_call_strike = None

        with c_cs:
            if collar_enabled and calls_df is not None and not calls_df.empty:
                calls_for_month = calls_df[calls_df['call_exp_month_display'] == sell_call_month].copy()
                if calls_for_month.empty:
                    st.info("Keine Calls für diesen Monat.")
                    collar_enabled = False
                else:
                    calls_for_month = calls_for_month.sort_values('strike_price')
                    call_labels = calls_for_month.apply(
                        lambda r: f"{r['strike_price']:.2f} (Prämie: {r['option_price']:.2f}$)",
                        axis=1,
                    ).tolist()
                    sel_call = st.selectbox("Call Strike", options=call_labels, key='call_strike_key')
                    if sel_call:
                        idx = call_labels.index(sel_call)
                        row = calls_for_month.iloc[idx]
                        selected_call_strike = float(row['strike_price'])
                        selected_call_price = float(row['option_price'])
            elif collar_enabled:
                st.info("Keine Calls verfügbar.")
                collar_enabled = False

        # ── Filters (collapsed) ────────────────────────────────────
        with st.expander("🔧 Filter", expanded=False):
            fc1, fc2 = st.columns(2)
            with fc1:
                max_profit_pct = df['locked_in_profit_pct'].max()
                if pd.isna(max_profit_pct) or max_profit_pct < 0:
                    max_profit_pct = 10.0
                min_profit_target = st.slider(
                    "Min. Locked-in Profit (%)", 0.0, float(max_profit_pct) + 5.0, 0.0, 0.5,
                )
            with fc2:
                min_open_interest = st.number_input(
                    "Min. Open Interest", min_value=0, value=0, step=10,
                )

        # ── Apply Filters ──────────────────────────────────────────
        display_df = (
            df[df['exp_month_display'] == selected_put_month].copy()
            if selected_put_month else df.copy()
        )
        if min_profit_target > 0:
            display_df = display_df[display_df['locked_in_profit_pct'] >= min_profit_target]
        if min_open_interest > 0:
            display_df = display_df[display_df['open_interest'] >= min_open_interest]

        # ── Collar Metrics ─────────────────────────────────────────
        if collar_enabled and selected_call_price is not None and selected_call_strike is not None:
            display_df = calculate_collar_metrics(
                display_df, selected_call_price, selected_call_strike, cost_basis_input,
            )
            puts_above_call = display_df[display_df['strike_price'] > selected_call_strike]
            if not puts_above_call.empty:
                st.warning(
                    f"⚠️ {len(puts_above_call)} Put(s) haben Strike > Call-Strike "
                    f"({selected_call_strike:.2f}$) – kein typischer Collar."
                )

        # ── Table ──────────────────────────────────────────────────
        if collar_enabled and 'collar_net_cost' in display_df.columns:
            header_title = f"Collar Analyse – {selected_put_month} / {sell_call_month}"
            base_cols = [
                'option_label', 'option_price', 'time_value', 'time_value_per_month',
                'collar_net_cost', 'collar_new_cost_basis',
                'collar_locked_in_profit', 'collar_locked_in_profit_pct',
                'pct_assigned', 'pct_assigned_with_put',
                'days_to_expiration', 'open_interest',
            ]
        else:
            header_title = f"Married Put Analyse – {selected_put_month or 'Alle'}"
            base_cols = [
                'option_label', 'option_price', 'time_value', 'time_value_per_month',
                'new_cost_basis', 'locked_in_profit', 'locked_in_profit_pct',
                'days_to_expiration', 'open_interest',
            ]

        st.markdown(f"### {header_title} ({len(display_df)} Optionen)")

        # Column config matching PowerOptions naming
        column_config = {
            "option_label": st.column_config.TextColumn("Put (Days)", width="large"),
            "option_price": st.column_config.NumberColumn("Put Midpoint Price To Buy", format="%.2f $"),
            "time_value": st.column_config.NumberColumn("Put Time Value", format="%.2f $"),
            "time_value_per_month": st.column_config.NumberColumn("Put Time Value /Mo", format="%.2f $"),
            "new_cost_basis": st.column_config.NumberColumn("New Cost Basis", format="%.2f $"),
            "locked_in_profit": st.column_config.NumberColumn("Locked In Profit", format="%.2f $"),
            "locked_in_profit_pct": st.column_config.NumberColumn("% Locked In Profit", format="%.2f %%"),
            "days_to_expiration": st.column_config.NumberColumn("DTE", format="%d"),
            "open_interest": st.column_config.NumberColumn("OI"),
            # Collar
            "collar_net_cost": st.column_config.NumberColumn("Net Cost", format="%.2f $"),
            "collar_new_cost_basis": st.column_config.NumberColumn("New Cost Basis", format="%.2f $"),
            "collar_locked_in_profit": st.column_config.NumberColumn("Locked In Profit", format="%.2f $"),
            "collar_locked_in_profit_pct": st.column_config.NumberColumn("% Locked In Profit", format="%.2f %%"),
            "pct_assigned": st.column_config.NumberColumn("% Assnd", format="%.2f %%"),
            "pct_assigned_with_put": st.column_config.NumberColumn("% Assnd w/ Put", format="%.2f %%"),
            # Hidden columns
            "symbol": None, "live_stock_price": None, "stock_close": None,
            "contract_type": None, "exp_month_sort": None, "exp_month_display": None,
            "greeks_delta": None, "greeks_theta": None, "intrinsic_value": None,
            "insurance_cost_pct": None, "annualized_cost": None, "annualized_cost_pct": None,
            "upside_drag_pct": None, "risk_pct": None, "downside_protection_pct": None,
            "strike_price": None, "expiration_date": None, "collar_max_profit": None,
            "collar_max_profit_pct": None,
        }

        cols_to_show = [c for c in base_cols if c in display_df.columns]
        display_ordered = display_df[cols_to_show].copy()
        if 'symbol' not in display_ordered.columns:
            display_ordered['symbol'] = display_df['symbol']

        page_display_dataframe(
            display_ordered, page='position_insurance',
            symbol_column='symbol', column_config=column_config,
        )

        # ── Tips & Documentation (collapsed) ───────────────────────
        with st.expander("📖 Tipps & Dokumentation", expanded=False):
            best_value = None
            if not display_df.empty:
                candidates = display_df[display_df['time_value_per_month'] > 0]
                if not candidates.empty:
                    best_value = candidates.loc[candidates['time_value_per_month'].idxmin()]
            if best_value is not None:
                st.info(
                    f"💡 **Effizienz-Tipp:** {best_value['option_label']} kostet nur "
                    f"**{best_value['time_value_per_month']:.2f}$/Monat** Zeitwert "
                    f"und sichert **{best_value['locked_in_profit_pct']:.1f}%** Gewinn."
                )
            best_prot = None
            if not display_df.empty:
                best_prot = display_df.loc[display_df['downside_protection_pct'].idxmin()]
            if best_prot is not None:
                st.info(
                    f"🛡️ **Bester Schutz:** {best_prot['option_label']} – "
                    f"Absicherung ab **{best_prot['downside_protection_pct']:.1f}%** unter Kurs, "
                    f"kostet **{best_prot['annualized_cost_pct']:.2f}% p.a.**"
                )
            st.divider()
            st.markdown(get_position_insurance_documentation())

# ── Footer links ────────────────────────────────────────────────────
st.divider()
st.markdown(
    "💡 [Smart Finder](/smart_finder) – Automatische Put-Empfehlungen &ensp;|&ensp; "
    "📊 [Call Income Simulator](/call_income_simulator) – Monatliche Call-Einnahmen planen"
)
