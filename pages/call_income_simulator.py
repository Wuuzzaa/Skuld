"""
Call Income Simulator – Streamlit page.

Wizard-style UI:
  Step 1  →  Symbol + Cost Basis → load data → pick a Put from dropdown
  Step 2  →  Call strategy (automatic / manual)
  Results →  Dashboard with metrics, table, chart, assignment scenario
"""

import logging
import os
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import PATH_DATABASE_QUERY_FOLDER
from src.call_income_simulator import (
    MONTH_MAP,
    MonthlyCall,
    build_auto_call_plan,
    calculate_assignment_scenario,
    find_otm_call_strike,
    simulate_call_income,
)
from src.database import select_into_dataframe
from src.logger_config import setup_logging

# ── Logging ─────────────────────────────────────────────────────────
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# ── Title ───────────────────────────────────────────────────────────
st.title("📊 Covered Call Income Simulator")
st.markdown(
    "Simuliere monatliche Call-Einnahmen auf eine bestehende Married-Put-Position. "
    "Ziel: Put-Kosten durch Call-Prämien decken (oder übertreffen)."
)

# ── Session state defaults ──────────────────────────────────────────
for key, default in [
    ("cis_puts_df", None),
    ("cis_calls_df", None),
    ("cis_symbol", ""),
    ("cis_current_price", 0.0),
    ("cis_result", None),
    ("cis_call_plan", None),
    ("cis_step", 1),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# =====================================================================
# STEP 1 – Symbol, Cost Basis & Put-Auswahl
# =====================================================================
st.subheader("Schritt 1: Position & Put auswählen")

c_sym, c_cb, c_btn = st.columns([2, 2, 1])
with c_sym:
    cis_symbol = st.text_input("Aktiensymbol", value=st.session_state.get("cis_symbol", ""), key="cis_sym").upper()
with c_cb:
    cis_cost_basis = st.number_input("Einstandskurs (Cost Basis)", min_value=0.01, value=35.0, step=0.5, format="%.2f", key="cis_cb")
with c_btn:
    st.write("")
    load_btn = st.button("📥 Daten laden", type="primary", use_container_width=True)

# Load puts + calls from DB
if load_btn and cis_symbol:
    with st.spinner(f"Lade Optionen für {cis_symbol}..."):
        try:
            params = {
                "symbol": cis_symbol,
                "today": pd.Timestamp.now().strftime("%Y-%m-%d"),
            }
            sql_path = PATH_DATABASE_QUERY_FOLDER / "position_insurance.sql"
            all_df = select_into_dataframe(sql_file_path=sql_path, params=params)

            if all_df.empty:
                st.warning(f"Keine Daten für {cis_symbol} gefunden.")
                st.session_state["cis_puts_df"] = None
                st.session_state["cis_calls_df"] = None
            else:
                current_price = all_df["live_stock_price"].iloc[0]
                if pd.isna(current_price):
                    current_price = all_df["stock_close"].iloc[0]

                puts_df = all_df[all_df["contract_type"] == "put"].copy()
                calls_df = all_df[all_df["contract_type"] == "call"].copy()

                if puts_df.empty:
                    st.warning("Keine Put-Optionen verfügbar.")
                    st.session_state["cis_puts_df"] = None
                else:
                    puts_df["expiration_date"] = pd.to_datetime(puts_df["expiration_date"])
                    st.session_state["cis_puts_df"] = puts_df

                if not calls_df.empty:
                    calls_df["expiration_date"] = pd.to_datetime(calls_df["expiration_date"])
                    calls_df = calls_df[calls_df["strike_price"] >= current_price].copy()
                    st.session_state["cis_calls_df"] = calls_df if not calls_df.empty else None
                else:
                    st.session_state["cis_calls_df"] = None

                st.session_state["cis_current_price"] = float(current_price)
                st.session_state["cis_symbol"] = cis_symbol
                st.session_state["cis_step"] = 1
                st.session_state["cis_result"] = None
                st.rerun()
        except Exception as e:
            st.error(f"Fehler: {e}")
            logger.error(e, exc_info=True)
elif load_btn:
    st.warning("Bitte ein Aktiensymbol eingeben.")

# ── Put selection (after data is loaded) ────────────────────────────
cis_put_strike = None
cis_put_price = None
cis_put_exp = None

if st.session_state["cis_puts_df"] is not None:
    puts_df = st.session_state["cis_puts_df"]
    cp = st.session_state["cis_current_price"]

    # Build put labels: "PLTR 2026 21-AUG 120.00 PUT (174) – 8.50$"
    puts_df = puts_df.copy()
    puts_df["put_label"] = puts_df.apply(
        lambda r: (
            f"{r['symbol']} {r['expiration_date'].year} "
            f"{r['expiration_date'].strftime('%d-%b').upper()} "
            f"{r['strike_price']:.2f} PUT ({int(r['days_to_expiration'])}) "
            f"– {r['option_price']:.2f}$"
        ), axis=1,
    )

    # Group by expiration month for optional filtering
    puts_df["exp_month"] = puts_df["expiration_date"].apply(lambda x: x.strftime("%Y-%m"))
    month_options = sorted(puts_df["exp_month"].unique())
    month_labels = {
        m: f"{m} ({MONTH_MAP.get(int(m.split('-')[1]), '')})" for m in month_options
    }

    pc1, pc2 = st.columns([1, 3])
    with pc1:
        sel_month = st.selectbox(
            "Put-Monat",
            options=month_options,
            format_func=lambda x: month_labels.get(x, x),
            key="cis_put_month",
        )
    with pc2:
        month_puts = puts_df[puts_df["exp_month"] == sel_month].sort_values("strike_price", ascending=False)
        if month_puts.empty:
            st.info("Keine Puts für diesen Monat.")
        else:
            sel_put_label = st.selectbox(
                "Put auswählen",
                options=month_puts["put_label"].tolist(),
                key="cis_put_select",
            )
            if sel_put_label:
                sel_put_row = month_puts[month_puts["put_label"] == sel_put_label].iloc[0]
                cis_put_strike = float(sel_put_row["strike_price"])
                cis_put_price = float(sel_put_row["option_price"])
                cis_put_exp = sel_put_row["expiration_date"].date()

    # Show derived info
    if cis_put_strike is not None:
        ncb = cis_cost_basis + cis_put_price
        lip = cis_put_strike - ncb
        lip_pct = (lip / ncb * 100) if ncb > 0 else 0

        st.success(
            f"**{st.session_state['cis_symbol']}** – Aktueller Kurs: **{cp:.2f}$** | "
            f"New Cost Basis (mit Put): **{ncb:.2f}$** | "
            f"Locked-in Profit: **{lip:.2f}$ ({lip_pct:.1f}%)** | "
            f"Put-Kosten zu decken: **{cis_put_price:.2f}$**"
        )

        # Advance to step 2
        st.session_state["cis_step"] = 2

# =====================================================================
# STEP 2 – Call strategy
# =====================================================================
if st.session_state.get("cis_step", 1) >= 2 and st.session_state["cis_calls_df"] is not None and cis_put_strike is not None:
    st.divider()
    st.subheader("Schritt 2: Call-Strategie")

    # Filter calls: only expirations before the selected put expiry
    calls_df = st.session_state["cis_calls_df"].copy()
    calls_df["expiration_date"] = pd.to_datetime(calls_df["expiration_date"])
    calls_df = calls_df[calls_df["expiration_date"].dt.date < cis_put_exp].copy()
    current_price = st.session_state["cis_current_price"]

    if calls_df.empty:
        st.warning("Keine Call-Optionen vor dem Put-Verfall verfügbar.")
    else:
        strategy = st.radio(
            "Wie willst du Calls verkaufen?",
            options=["auto", "manual"],
            format_func=lambda x: {
                "auto": "🤖 Automatisch – Jeden Monat X% OTM",
                "manual": "✋ Manuell – Strikes pro Monat wählen",
            }[x],
            horizontal=True,
            key="cis_strategy",
        )

        call_plan: list[MonthlyCall] = []

        # ── Automatic mode ──────────────────────────────────────────
        if strategy == "auto":
            otm_option = st.radio(
                "Call-Strike-Präferenz",
                options=["atm", "5_otm", "10_otm", "custom"],
                format_func=lambda x: {
                    "atm": "ATM (am Geld – höchste Prämie)",
                    "5_otm": "5% OTM",
                    "10_otm": "10% OTM (konservativ)",
                    "custom": "Custom %",
                }[x],
                horizontal=True,
                key="cis_otm_choice",
            )

            otm_pct_map = {"atm": 0.0, "5_otm": 5.0, "10_otm": 10.0, "custom": 10.0}
            otm_pct = otm_pct_map[otm_option]
            if otm_option == "custom":
                otm_pct = st.number_input("OTM %", min_value=0.0, max_value=50.0, value=10.0, step=1.0, key="cis_custom_otm")

            call_plan = build_auto_call_plan(current_price, cis_put_exp, otm_pct, calls_df)

            if call_plan:
                st.info(
                    f"⚠️ Die Simulation nutzt den heutigen Kurs ({current_price:.2f}$) als Basis "
                    f"für die Call-Strike-Berechnung aller Monate. In der Praxis würdest du "
                    f"jeden Monat neu entscheiden."
                )
                st.markdown(f"**Vorschau:** {len(call_plan)} Calls geplant")
                preview_data = [
                    {
                        "Monat": c.month_label,
                        "Strike": f"{c.strike:.2f}",
                        "Prämie": f"{c.premium:.2f}$",
                        "DTE": c.days_to_expiration,
                        "OI": c.open_interest,
                    }
                    for c in call_plan
                ]
                st.dataframe(pd.DataFrame(preview_data), hide_index=True, use_container_width=True)
            else:
                st.warning("Keine Call-Optionen für den automatischen Plan gefunden.")

        # ── Manual mode ─────────────────────────────────────────────
        else:
            # Group available calls by month
            mc = calls_df.copy()
            mc["expiration_date"] = pd.to_datetime(mc["expiration_date"])
            mc["year_month"] = mc["expiration_date"].apply(lambda x: x.strftime("%Y-%m"))
            mc["exp_date"] = mc["expiration_date"].dt.date

            available_months = sorted(mc["year_month"].unique())

            if not available_months:
                st.warning("Keine Verfallsmonate für Calls verfügbar.")
            else:
                st.markdown("Wähle für jeden Monat einen Call:")
                manual_calls: list[MonthlyCall] = []

                for ym in available_months:
                    month_data = mc[mc["year_month"] == ym]
                    latest_exp = month_data["exp_date"].max()
                    month_num = latest_exp.month
                    label = f"{ym} ({MONTH_MAP.get(month_num, '')})"

                    month_calls = month_data[month_data["exp_date"] == latest_exp].sort_values("strike_price")
                    strikes = month_calls["strike_price"].unique().tolist()

                    cols = st.columns([0.5, 2, 2.5, 1.5, 1])
                    with cols[0]:
                        enabled = st.checkbox("", value=True, key=f"cis_chk_{ym}")
                    with cols[1]:
                        st.markdown(f"**{label}**")
                    with cols[2]:
                        if enabled and strikes:
                            # Default: nearest OTM strike
                            default_strike = find_otm_call_strike(strikes, current_price, 5.0)
                            default_idx = strikes.index(default_strike) if default_strike in strikes else 0
                            sel_strike = st.selectbox(
                                "Strike", options=strikes, index=default_idx,
                                key=f"cis_strike_{ym}", label_visibility="collapsed",
                                format_func=lambda x: f"{x:.2f}",
                            )
                        else:
                            sel_strike = None
                            st.write("—")

                    with cols[3]:
                        if enabled and sel_strike is not None:
                            row = month_calls[month_calls["strike_price"] == sel_strike].iloc[0]
                            premium = float(row["option_price"])
                            st.write(f"{premium:.2f}$")
                        else:
                            premium = 0.0
                            st.write("—")

                    with cols[4]:
                        if enabled and sel_strike is not None:
                            oi = int(row["open_interest"])
                            st.write(f"OI: {oi}")
                        else:
                            oi = 0
                            st.write("")

                    if enabled and sel_strike is not None:
                        manual_calls.append(MonthlyCall(
                            month_label=label,
                            expiration_date=latest_exp,
                            strike=float(sel_strike),
                            premium=premium,
                            days_to_expiration=int(row["days_to_expiration"]),
                            open_interest=oi,
                        ))

                call_plan = manual_calls

        # ── Simulate button ─────────────────────────────────────────
        st.divider()
        sim_btn = st.button("🚀 Simulation starten", type="primary", use_container_width=True)

        if sim_btn and call_plan:
            result = simulate_call_income(
                symbol=st.session_state["cis_symbol"],
                cost_basis=cis_cost_basis,
                current_price=current_price,
                put_strike=cis_put_strike,
                put_price=cis_put_price,
                put_expiration_date=cis_put_exp,
                call_plan=call_plan,
            )
            st.session_state["cis_result"] = result
            st.session_state["cis_call_plan"] = call_plan
            st.rerun()
        elif sim_btn:
            st.warning("Keine Calls im Plan – bitte mindestens einen Monat aktivieren.")

# =====================================================================
# RESULTS
# =====================================================================
if st.session_state.get("cis_result") is not None:
    result = st.session_state["cis_result"]

    st.divider()
    st.subheader(f"📊 Call-Income-Simulation: {result.symbol}")

    # ── Header metrics ──────────────────────────────────────────────
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Put-Kosten", f"{result.put_price:.2f}$")
    h2.metric("Call-Einnahmen", f"{result.total_call_income:.2f}$")
    h3.metric(
        "Netto-Kosten",
        f"{result.net_insurance_cost:.2f}$",
        delta="Credit!" if result.net_insurance_cost < 0 else None,
        delta_color="normal" if result.net_insurance_cost < 0 else "inverse",
    )
    h4.metric(
        "Breakeven nach",
        f"{result.months_to_breakeven} Monaten" if result.months_to_breakeven else "Nicht erreicht",
    )

    # ── Progress bar – put cost coverage ────────────────────────────
    coverage = min(result.put_cost_covered_pct / 100, 1.0)
    st.progress(coverage, text=f"Put-Kosten gedeckt: {result.put_cost_covered_pct:.0f}%")

    # ── Effective metrics ───────────────────────────────────────────
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Eff. Einstandskurs", f"{result.effective_cost_basis:.2f}$",
              delta=f"vorher: {result.cost_basis + result.put_price:.2f}$", delta_color="off")
    e2.metric("Eff. Locked-in Profit", f"{result.effective_locked_in_profit:.2f}$")
    e3.metric("Eff. Locked-in %", f"{result.effective_locked_in_profit_pct:.1f}%")
    e4.metric("⌀ monatl. Einnahme", f"{result.avg_monthly_income:.2f}$ ({result.avg_monthly_income_pct:.1f}%)")

    # ── Feedback messages ───────────────────────────────────────────
    if result.total_call_income > result.put_price * 2:
        st.success(
            f"🎉 Deine Call-Einnahmen ({result.total_call_income:.2f}$) decken die "
            f"Put-Kosten ({result.put_price:.2f}$) mehr als doppelt. "
            f"Die Absicherung ist effektiv kostenlos + Bonus."
        )
    elif result.months_to_breakeven is None:
        remaining = result.put_price - result.total_call_income
        st.warning(
            f"Put-Kosten werden in den geplanten {len(result.call_plan)} Monaten "
            f"nicht vollständig gedeckt. Es fehlen noch {remaining:.2f}$ "
            f"({100 - result.put_cost_covered_pct:.0f}%)."
        )

    # Check warnings
    if any(c.strike < result.current_price for c in result.call_plan):
        st.warning(
            "⚠️ Ein oder mehrere Calls liegen ITM (unter aktuellem Kurs). "
            "Das bedeutet hohes Assignment-Risiko bereits beim Verkauf."
        )
    if any(c.strike < result.put_strike for c in result.call_plan):
        st.warning(
            "⚠️ Ein oder mehrere Call-Strikes liegen unter dem Put-Strike. "
            "Bei Assignment wäre der Put noch im Geld – prüfe ob das gewollt ist."
        )

    st.divider()

    # ── Monthly breakdown table ─────────────────────────────────────
    st.subheader("Monatsweise Aufschlüsselung")

    details_df = pd.DataFrame(result.monthly_details)
    if not details_df.empty:
        display_cols = {
            "month_label": "Monat",
            "strike": "Call-Strike",
            "premium": "Call-Prämie ($)",
            "cumulative": "Kumuliert ($)",
            "put_covered_pct": "Put gedeckt (%)",
            "assignment_buffer_pct": "Assignment-Puffer (%)",
            "status": "Status",
        }
        table_df = details_df[list(display_cols.keys())].rename(columns=display_cols)
        st.dataframe(
            table_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Call-Strike": st.column_config.NumberColumn(format="%.2f"),
                "Call-Prämie ($)": st.column_config.NumberColumn(format="%.2f"),
                "Kumuliert ($)": st.column_config.NumberColumn(format="%.2f"),
                "Put gedeckt (%)": st.column_config.NumberColumn(format="%.1f"),
                "Assignment-Puffer (%)": st.column_config.NumberColumn(format="%.1f"),
            },
        )

    # ── Cumulative chart ────────────────────────────────────────────
    if not details_df.empty:
        fig = go.Figure()

        months = details_df["month_label"].tolist()
        cumulative_vals = details_df["cumulative"].tolist()
        colors = [
            "#ef4444" if c < result.put_price else "#22c55e" for c in cumulative_vals
        ]

        fig.add_trace(go.Bar(
            x=months,
            y=cumulative_vals,
            name="Kumulierte Call-Prämien",
            marker_color=colors,
        ))

        fig.add_hline(
            y=result.put_price,
            line_dash="dash",
            line_color="white",
            annotation_text=f"Put-Kosten: {result.put_price:.2f}$",
            annotation_font_color="white",
        )

        fig.update_layout(
            title="Kumulative Call-Einnahmen vs. Put-Kosten",
            xaxis_title="Monat",
            yaxis_title="$ (kumuliert)",
            template="plotly_dark",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Assignment scenario (expander) ──────────────────────────────
    with st.expander("⚠️ Assignment-Szenario", expanded=False):
        st.markdown(
            "Was passiert, wenn die Aktie in einem Monat über deinen Call-Strike steigt "
            "und du assigned wirst?"
        )
        if result.monthly_details:
            cumulative_so_far = 0.0
            for detail in result.monthly_details:
                call_obj = MonthlyCall(
                    month_label=detail["month_label"],
                    expiration_date=detail["expiration_date"],
                    strike=detail["strike"],
                    premium=detail["premium"],
                    days_to_expiration=detail["days_to_expiration"],
                    open_interest=detail["open_interest"],
                )
                scenario = calculate_assignment_scenario(
                    call_obj, result.cost_basis, result.put_price,
                    result.put_strike, cumulative_so_far,
                )
                put_note = (
                    f" (Put hat Restwert: {scenario['put_residual_value']:.2f}$)"
                    if scenario["put_residual_value"] > 0 else
                    " (Put verfällt wertlos)"
                )
                st.markdown(
                    f"**{detail['month_label']}** (Strike {detail['strike']:.2f}): "
                    f"Gewinn bei Assignment = **{scenario['total_return']:.2f}$** "
                    f"({scenario['total_return_pct']:.1f}%){put_note}"
                )
                cumulative_so_far += detail["premium"]

    # ── Disclaimer ──────────────────────────────────────────────────
    with st.expander("ℹ️ Wichtige Hinweise", expanded=False):
        st.markdown("""
**1. HEUTIGER KURS ALS BASIS:** Alle Call-Prämien basieren auf den heutigen
Marktdaten. In der Praxis ändern sich Kurs, Volatilität und Prämien täglich.
Die tatsächlichen Prämien werden abweichen.

**2. KEIN KURS-SZENARIO:** Die Simulation geht davon aus, dass der Aktienkurs
ungefähr auf dem heutigen Niveau bleibt. Bei starken Kursbewegungen ändern
sich die verfügbaren Prämien erheblich.

**3. KEIN ASSIGNMENT-MODELL:** Die Simulation zeigt, was du an Prämien
einnehmen KÖNNTEST. Wenn die Aktie in einem Monat über den Call-Strike steigt,
wird die Aktie abgerufen und die Simulation endet de facto.

**4. MIDPOINT ≠ FILL-PREIS:** Die angezeigten Prämien sind Midpoints. Der
tatsächliche Fill-Preis kann abweichen, besonders bei niedrigem OI.
        """)

# ── Footer ──────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "🛡️ [Position Insurance Tool](/position_insurance_tool) &ensp;|&ensp; "
    "🔍 [Smart Finder](/smart_finder)"
)
