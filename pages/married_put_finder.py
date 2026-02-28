"""
Married Put Finder – Streamlit page.

PowerOptions-style UI for the RadioActive Trading method:
  • Symbol + Cost Basis + Buy Put Month + Sell Call Month → CALCULATE
  • ATM / OTM strike filter
  • Clean table output matching PowerOptions column layout with colour contrast
"""

import logging
import os

import pandas as pd
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.married_put_finder import (
    MONTH_MAP,
    calculate_collar_metrics,
    calculate_put_only_metrics,
    filter_strikes_by_moneyness,
    get_month_options,
    get_month_options_with_dte,
)
from src.page_display_dataframe import page_display_dataframe

# ── Logging ─────────────────────────────────────────────────────────
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# ── Page Title ──────────────────────────────────────────────────────
st.title("🎯 Married Put Finder")
st.caption(
    "RadioActive Trading – Finde geeignete Puts zur Absicherung "
    "und optionale Calls zur Finanzierung."
)

# ── Session State ───────────────────────────────────────────────────
for key, default in [
    ("mpf_puts_df", None),
    ("mpf_calls_df", None),
    ("mpf_symbol", ""),
    ("mpf_current_price", 0.0),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Input Row (PowerOptions-style) ─────────────────────────────────
c_sym, c_cb, c_btn = st.columns([2, 2, 1])
with c_sym:
    symbol_input = st.text_input(
        "Stock Symbol",
        value=st.session_state.get("mpf_symbol", ""),
        key="mpf_sym_input",
    ).upper()
with c_cb:
    cost_basis_input = st.number_input(
        "Cost Basis/Shr",
        min_value=0.01,
        value=100.0,
        step=0.5,
        format="%.2f",
        key="mpf_cb_input",
    )
with c_btn:
    st.write("")  # vertical spacing
    load_btn = st.button("CALCULATE", type="primary", use_container_width=True)

# ── Load Data ───────────────────────────────────────────────────────
if load_btn and symbol_input:
    with st.spinner(f"Lade Optionen für {symbol_input}..."):
        try:
            params = {
                "symbol": symbol_input,
                "today": pd.Timestamp.now().strftime("%Y-%m-%d"),
            }
            sql_path = PATH_DATABASE_QUERY_FOLDER / "position_insurance.sql"
            all_df = select_into_dataframe(sql_file_path=sql_path, params=params)

            if all_df.empty:
                st.warning(f"Keine Daten für {symbol_input} gefunden.")
                st.session_state["mpf_puts_df"] = None
                st.session_state["mpf_calls_df"] = None
            else:
                current_price = all_df["live_stock_price"].iloc[0]
                if pd.isna(current_price):
                    current_price = all_df["stock_close"].iloc[0]

                puts_df = all_df[all_df["contract_type"] == "put"].copy()
                calls_df = all_df[all_df["contract_type"] == "call"].copy()

                st.session_state["mpf_puts_df"] = puts_df if not puts_df.empty else None
                st.session_state["mpf_calls_df"] = calls_df if not calls_df.empty else None
                st.session_state["mpf_current_price"] = float(current_price)
                st.session_state["mpf_symbol"] = symbol_input
                st.rerun()
        except Exception as e:
            st.error(f"Fehler: {e}")
            logger.error(e, exc_info=True)
elif load_btn:
    st.warning("Bitte ein Aktiensymbol eingeben.")

# =====================================================================
# DISPLAY
# =====================================================================
if st.session_state["mpf_puts_df"] is not None:
    puts_df = st.session_state["mpf_puts_df"].copy()
    calls_df = st.session_state["mpf_calls_df"]
    current_price = st.session_state["mpf_current_price"]
    symbol = st.session_state["mpf_symbol"]

    # ── Info banner ─────────────────────────────────────────────────
    profit = current_price - cost_basis_input
    profit_pct = (profit / cost_basis_input * 100) if cost_basis_input > 0 else 0
    st.success(
        f"**{symbol}** – Current Price: **{current_price:.2f}$** &ensp;|&ensp; "
        f"Your Current Profit: **{profit:+.2f} ({profit_pct:+.1f}%)**"
    )

    # ── Month dropdowns + Strike filter ─────────────────────────────
    puts_df["expiration_date"] = pd.to_datetime(puts_df["expiration_date"])
    put_month_opts = get_month_options_with_dte(puts_df)

    # Prepare call months (only if calls exist)
    call_month_opts: list[tuple[str, str]] = []
    if calls_df is not None and not calls_df.empty:
        calls_df = calls_df.copy()
        calls_df["expiration_date"] = pd.to_datetime(calls_df["expiration_date"])
        # Note: strike filtering (call_strike >= put_strike) is done in the
        # calculation engine, so we keep all OTM calls here for the dropdown.
        if not calls_df.empty:
            call_month_opts = get_month_options_with_dte(calls_df)

    c_pm, c_cm, c_flt = st.columns([2, 2, 2])
    with c_pm:
        put_month_labels = [label for _, label in put_month_opts]
        sel_put_month_label = st.selectbox(
            "Buy Put Month",
            options=put_month_labels,
            index=0 if put_month_labels else None,
            key="mpf_put_month",
        )
    with c_cm:
        call_month_labels = ["None"] + [label for _, label in call_month_opts]
        sel_call_month_label = st.selectbox(
            "Sell Call Month",
            options=call_month_labels,
            index=0,
            key="mpf_call_month",
        )
    with c_flt:
        moneyness_options = {
            "atm": f"ATM ± 5% ({current_price * 0.95:.0f}–{current_price * 1.05:.0f})",
            "atm_10": f"ATM bis +10% ({current_price * 0.95:.0f}–{current_price * 1.10:.0f})",
            "atm_20": f"ATM bis +20% ({current_price * 0.95:.0f}–{current_price * 1.20:.0f})",
            "atm_30": f"ATM bis +30% ({current_price * 0.95:.0f}–{current_price * 1.30:.0f})",
            "all": "Alle Strikes",
        }
        sel_moneyness = st.selectbox(
            "Strike-Filter",
            options=list(moneyness_options.keys()),
            format_func=lambda x: moneyness_options[x],
            index=2,  # default: ATM to +20%
            key="mpf_moneyness",
        )

    # Resolve selection to sort keys
    sel_put_ym = None
    for ym, label in put_month_opts:
        if label == sel_put_month_label:
            sel_put_ym = ym
            break

    collar_enabled = sel_call_month_label != "None"
    sel_call_ym = None
    if collar_enabled:
        for ym, label in call_month_opts:
            if label == sel_call_month_label:
                sel_call_ym = ym
                break

    # ── Filter puts by selected month ───────────────────────────────
    if sel_put_ym:
        puts_df["ym"] = puts_df["expiration_date"].apply(lambda x: x.strftime("%Y-%m"))
        filtered_puts = puts_df[puts_df["ym"] == sel_put_ym].copy()
    else:
        filtered_puts = puts_df.copy()

    # Only puts with strike >= cost basis (meaningful protection)
    filtered_puts = filtered_puts[
        filtered_puts["strike_price"] >= cost_basis_input
    ].copy()

    # Apply moneyness filter
    filtered_puts = filter_strikes_by_moneyness(
        filtered_puts, current_price, mode=sel_moneyness,
    )

    if filtered_puts.empty:
        st.info("Keine Put-Optionen für diese Filter-Kombination gefunden.")
    else:
        # ── Calculate metrics ───────────────────────────────────────
        if collar_enabled and sel_call_ym and calls_df is not None:
            # Filter calls by selected call month
            calls_df_c = calls_df.copy()
            calls_df_c["ym"] = calls_df_c["expiration_date"].apply(
                lambda x: x.strftime("%Y-%m")
            )
            month_calls = calls_df_c[calls_df_c["ym"] == sel_call_ym].copy()

            result_df = calculate_collar_metrics(
                filtered_puts, month_calls, cost_basis_input, current_price,
            )
        else:
            result_df = calculate_put_only_metrics(
                filtered_puts, cost_basis_input, current_price,
            )

        # ── Sort by locked-in profit descending ───────────────────
        result_df = result_df.sort_values("locked_in_profit_pct", ascending=False)

        # ── Build display table ─────────────────────────────────────
        if collar_enabled and "call_label" in result_df.columns:
            # Collar view – Put + Call columns
            display_cols = [
                "put_label",
                "put_midpoint_price",
                "put_time_value",
                "put_time_value_per_mo",
                "call_label",
                "call_midpoint_price",
                "new_cost_basis",
                "locked_in_profit",
                "locked_in_profit_pct",
                "pct_assigned",
                "pct_assigned_with_put",
            ]
            header = f"Collar – {sel_put_month_label} / {sel_call_month_label}"
        else:
            # Put-only view
            display_cols = [
                "put_label",
                "put_midpoint_price",
                "put_time_value",
                "put_time_value_per_mo",
                "new_cost_basis",
                "locked_in_profit",
                "locked_in_profit_pct",
            ]
            header = f"Married Put – {sel_put_month_label}"

        cols_present = [c for c in display_cols if c in result_df.columns]
        display_df = result_df[cols_present].copy()

        st.markdown(f"### {header} ({len(display_df)} Optionen)")

        # ── Styled dataframe with column contrast ──────────────────
        #    Alternate background colours per column group so the
        #    table is easier to scan (like PowerOptions).
        col_put = "background-color: rgba(30, 58, 95, 0.35);"       # dark blue-ish
        col_call = "background-color: rgba(20, 83, 45, 0.35);"      # dark green-ish
        col_metric = "background-color: rgba(120, 53, 15, 0.30);"   # dark amber-ish
        col_profit = "background-color: rgba(88, 28, 135, 0.30);"   # dark purple-ish

        col_styles = {
            "put_label": col_put,
            "put_midpoint_price": col_put,
            "put_time_value": col_put,
            "put_time_value_per_mo": col_put,
            "call_label": col_call,
            "call_midpoint_price": col_call,
            "new_cost_basis": col_metric,
            "locked_in_profit": col_profit,
            "locked_in_profit_pct": col_profit,
            "pct_assigned": col_metric,
            "pct_assigned_with_put": col_metric,
        }

        def _style_columns(styler):
            for col_name in styler.columns:
                if col_name in col_styles:
                    styler = styler.set_properties(
                        subset=[col_name], **{"cssStyles": col_styles[col_name]}
                    )
            return styler

        # Format numbers
        format_dict = {
            "put_midpoint_price": "{:.2f} $",
            "put_time_value": "{:.2f} $",
            "put_time_value_per_mo": "{:.2f} $",
            "call_midpoint_price": "{:.2f} $",
            "new_cost_basis": "{:.2f} $",
            "locked_in_profit": "{:.2f} $",
            "locked_in_profit_pct": "{:.1f} %",
            "pct_assigned": "{:.1f} %",
            "pct_assigned_with_put": "{:.1f} %",
        }
        active_format = {k: v for k, v in format_dict.items() if k in display_df.columns}

        # Rename columns for display (PowerOptions naming)
        rename_map = {
            "put_label": "Put (DTE)",
            "put_midpoint_price": "Put Midpoint Price To Buy",
            "put_time_value": "Put Time Value",
            "put_time_value_per_mo": "Put Time Value /Mo",
            "call_label": "Call (DTE)",
            "call_midpoint_price": "Call Midpoint Price To Sell",
            "new_cost_basis": "New Cost Basis",
            "locked_in_profit": "Locked In Profit",
            "locked_in_profit_pct": "% Locked In Profit",
            "pct_assigned": "% Assnd",
            "pct_assigned_with_put": "% Assnd w/ Put",
        }

        styled_df = display_df.copy()
        styled_df.rename(columns=rename_map, inplace=True)
        renamed_format = {rename_map.get(k, k): v for k, v in active_format.items()}
        renamed_styles = {rename_map.get(k, k): v for k, v in col_styles.items()}

        def _apply_col_bg(styler):
            for col_name in styler.columns:
                if col_name in renamed_styles:
                    styler = styler.set_properties(
                        subset=[col_name], **{"background-color": ""},
                    )
            return styler

        # Use Pandas Styler for column-level background colours
        styler = styled_df.style.format(renamed_format, na_rep="—")

        # Apply column-group background colours
        put_cols_renamed = [rename_map.get(c, c) for c in ["put_label", "put_midpoint_price", "put_time_value", "put_time_value_per_mo"] if c in cols_present]
        call_cols_renamed = [rename_map.get(c, c) for c in ["call_label", "call_midpoint_price"] if c in cols_present]
        metric_cols_renamed = [rename_map.get(c, c) for c in ["new_cost_basis", "pct_assigned", "pct_assigned_with_put"] if c in cols_present]
        profit_cols_renamed = [rename_map.get(c, c) for c in ["locked_in_profit", "locked_in_profit_pct"] if c in cols_present]

        if put_cols_renamed:
            styler = styler.set_properties(subset=put_cols_renamed, **{"background-color": "rgba(30, 58, 95, 0.35)"})
        if call_cols_renamed:
            styler = styler.set_properties(subset=call_cols_renamed, **{"background-color": "rgba(20, 83, 45, 0.35)"})
        if metric_cols_renamed:
            styler = styler.set_properties(subset=metric_cols_renamed, **{"background-color": "rgba(120, 53, 15, 0.30)"})
        if profit_cols_renamed:
            styler = styler.set_properties(subset=profit_cols_renamed, **{"background-color": "rgba(88, 28, 135, 0.30)"})

        styler = styler.hide(axis="index")

        st.dataframe(
            styler,
            use_container_width=True,
            height=min(800, 40 + 35 * len(display_df)),
        )

        # ── Quick tips (collapsed) ─────────────────────────────────
        with st.expander("ℹ️ Erklärung", expanded=False):
            st.markdown("""
**Put Midpoint Price To Buy** – Midpoint-Preis des Puts (premium_option_price).

**Put Time Value** – Zeitwert = Midpoint minus innerer Wert.
Je niedriger, desto effizienter die Versicherung.

**Put Time Value /Mo** – Zeitwert pro 30 Tage.
Vergleichbar über verschiedene Laufzeiten.

**New Cost Basis** – Einstand + Put-Midpoint (− Call-Midpoint bei Collar).

**Locked In Profit** – Strike − New Cost Basis.
Positiv = garantierter Mindestgewinn bei Ausübung.

**% Assnd** – Gewinn wenn die Aktie am Call-Strike abgerufen wird.

**% Assnd w/ Put** – Wie % Assnd, aber berücksichtigt den
Restwert des Puts falls Put-Strike > Call-Strike.

---

**Collar-Kombinationslogik:**
- Für jeden Put werden **alle** Calls mit Strike ≥ Put-Strike kombiniert
- **Same-Strike-Collar** (Put 170 + Call 170): Max. Locked-In Profit, aber Cap beim selben Strike
- **Wide Collar** (Put 140 + Call 150): Weniger Locked-In Profit, aber mehr Upside bis zum Call-Strike
- Unterschied zwischen % Assnd und % Assnd w/ Put zeigt den zusätzlichen Wert durch den Put-Restwert

**Farbcodierung:** 🔵 Put-Daten | 🟢 Call-Daten | 🟠 Metriken | 🟣 Profit
            """)

# ── Footer ──────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "🛡️ [Position Insurance Tool](/position_insurance_tool) &ensp;|&ensp; "
    "📊 [Call Income Simulator](/call_income_simulator) &ensp;|&ensp; "
    "🔍 [Smart Finder](/smart_finder)"
)
