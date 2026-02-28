import logging
import os
import streamlit as st
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.position_insurance_calculation import calculate_position_insurance_metrics
from src.smart_finder_engine import (
    HOLDING_PERIOD_MAP,
    DEFAULT_WEIGHTS,
    apply_quality_filters,
    calculate_smart_scores,
    get_top_recommendations,
    generate_comparison_insight,
)

# ── Logging ─────────────────────────────────────────────────────────
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# ── Page header ─────────────────────────────────────────────────────
st.title("🔍 Position Insurance – Smart Finder")
st.markdown("""
Automatische Suche nach der optimalen Put-Absicherung **über alle Verfallsmonate hinweg**.
Beantworte drei kurze Fragen – der Smart Finder durchsucht, filtert und bewertet alle Optionen für dich.

📋 *Für manuelles Feintuning → [Position Insurance Tool](/position_insurance_tool)*
""")

# ── Session state ───────────────────────────────────────────────────
for key, default in [
    ("sf_results_df", None),
    ("sf_symbol", ""),
    ("sf_step", 1),
    ("sf_filter_stats", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# =====================================================================
# WIZARD
# =====================================================================

# ── Step 1: Basis-Daten ─────────────────────────────────────────────
st.subheader("Schritt 1: Basis-Daten")
col_s1, col_s2, col_s3 = st.columns(3)
with col_s1:
    sf_symbol = st.text_input("Aktiensymbol", value=st.session_state.get("sf_symbol", ""), key="sf_sym_input").upper()
with col_s2:
    sf_cost_basis = st.number_input("Einstandskurs (Cost Basis)", min_value=0.01, value=100.0, step=0.5, format="%.2f", key="sf_cb")
with col_s3:
    sf_num_shares = st.number_input("Anzahl Aktien (optional)", min_value=1, value=100, step=100, key="sf_shares",
                                     help="Für Dollar-Beträge. Standard: 100 (= 1 Kontrakt)")

st.divider()

# ── Step 2: Ziel ────────────────────────────────────────────────────
st.subheader("Schritt 2: Dein Ziel")
goal_option = st.radio(
    "Was willst du erreichen?",
    options=["lock_profit", "limit_loss", "cheapest"],
    format_func=lambda x: {
        "lock_profit": "🔒 Gewinn absichern (Locked-in Profit > 0%)",
        "limit_loss": "🛑 Verlust begrenzen (Max. Verlust definieren)",
        "cheapest": "💰 Egal – zeig mir die günstigsten Optionen",
    }[x],
    horizontal=True,
    key="sf_goal",
)

if goal_option == "lock_profit":
    sf_min_profit_pct = st.slider("Min. Gewinn sichern (%)", 0.0, 300.0, 50.0, 5.0, key="sf_min_profit",
                                   help="z.B. 100% = Verdopplung des Einsatzes absichern")
elif goal_option == "limit_loss":
    sf_max_loss_pct = st.slider("Max. akzeptabler Verlust (%)", 0.0, 50.0, 10.0, 1.0, key="sf_max_loss",
                                 help="z.B. 10% = höchstens 10% Verlust")
    # Convert loss target to a minimum locked-in profit (can be negative)
    # locked_in_profit_pct >= -max_loss_pct  → we pass this differently in scoring
    sf_min_profit_pct = -sf_max_loss_pct
else:
    sf_min_profit_pct = 0.0

st.divider()

# ── Step 3: Haltedauer ──────────────────────────────────────────────
st.subheader("Schritt 3: Haltedauer")
holding = st.radio(
    "Wie lange willst du die Aktie noch halten?",
    options=["short", "medium", "long", "any"],
    format_func=lambda x: {
        "short": "⏱️ Kurzfristig (1-3 Monate)",
        "medium": "📅 Mittelfristig (3-6 Monate)",
        "long": "📆 Langfristig (6-12 Monate)",
        "any": "🤷 Egal / Unsicher – alle Laufzeiten",
    }[x],
    horizontal=True,
    key="sf_holding",
)

st.divider()

# ── Advanced settings (expander) ────────────────────────────────────
with st.expander("⚙️ Erweiterte Einstellungen", expanded=False):
    adv1, adv2 = st.columns(2)
    with adv1:
        adv_min_oi = st.slider("Min. Open Interest", 1, 500, 10, key="sf_adv_oi",
                                help="Höhere Werte = nur liquidere Optionen")
        adv_max_cost = st.slider("Max. Versicherungskosten (%)", 1.0, 50.0, 20.0, key="sf_adv_cost",
                                  help="Optionen über diesem Wert werden ausgeschlossen")
    with adv2:
        adv_min_delta = st.slider("Min. |Delta|", 0.00, 0.20, 0.01, 0.01, key="sf_adv_delta",
                                   help="Extrem weit OTM Puts herausfiltern")
        adv_top_n = st.slider("Max. Ergebnisse anzeigen", 5, 50, 15, key="sf_adv_topn",
                               help="Anzahl Zeilen in der Vergleichstabelle")

with st.expander("🎚️ Scoring-Gewichtung anpassen", expanded=False):
    w_cost = st.slider("Kosten-Effizienz", 0, 100, 30, key="sf_w_cost")
    w_protection = st.slider("Schutz-Level", 0, 100, 25, key="sf_w_prot")
    w_liquidity = st.slider("Liquidität", 0, 100, 15, key="sf_w_liq")
    w_dte = st.slider("Laufzeit-Match", 0, 100, 15, key="sf_w_dte")
    w_tv = st.slider("Zeitwert-Effizienz", 0, 100, 15, key="sf_w_tv")

    total_w = w_cost + w_protection + w_liquidity + w_dte + w_tv
    if total_w > 0:
        custom_weights = {
            "cost": w_cost / total_w,
            "protection": w_protection / total_w,
            "liquidity": w_liquidity / total_w,
            "dte_match": w_dte / total_w,
            "time_value": w_tv / total_w,
        }
    else:
        custom_weights = DEFAULT_WEIGHTS

# =====================================================================
# SEARCH
# =====================================================================
search_btn = st.button("🔍 Suche starten", type="primary", use_container_width=True)

if search_btn and sf_symbol:
    with st.spinner(f"Durchsuche alle Optionen für {sf_symbol}..."):
        try:
            params = {
                "symbol": sf_symbol,
                "today": pd.Timestamp.now().strftime('%Y-%m-%d'),
            }
            sql_path = PATH_DATABASE_QUERY_FOLDER / 'position_insurance.sql'
            all_df = select_into_dataframe(sql_file_path=sql_path, params=params)

            if all_df.empty:
                st.warning(f"Keine Optionen für {sf_symbol} gefunden.")
                st.session_state["sf_results_df"] = None
            else:
                # Only puts for Smart Finder
                puts_df = all_df[all_df['contract_type'] == 'put'].copy()
                if puts_df.empty:
                    st.warning(f"Keine Put-Optionen für {sf_symbol} gefunden.")
                    st.session_state["sf_results_df"] = None
                else:
                    current_price = puts_df['live_stock_price'].iloc[0]
                    if pd.isna(current_price):
                        current_price = puts_df['stock_close'].iloc[0]
                    puts_df['live_stock_price'] = current_price

                    # Calculate Married-Put metrics
                    puts_df = calculate_position_insurance_metrics(puts_df, sf_cost_basis)

                    # Pre-filter: strike >= cost_basis (for lock_profit / cheapest goals)
                    if goal_option in ("lock_profit", "cheapest"):
                        puts_df = puts_df[puts_df['strike_price'] >= sf_cost_basis].copy()

                    # Quality filter
                    filtered_df, stats = apply_quality_filters(
                        puts_df,
                        min_open_interest=adv_min_oi,
                        min_dte=7,
                        max_insurance_cost_pct=adv_max_cost,
                        min_abs_delta=adv_min_delta,
                    )

                    st.session_state["sf_filter_stats"] = stats
                    st.session_state["sf_symbol"] = sf_symbol

                    if filtered_df.empty:
                        st.warning("Alle Optionen wurden durch die Qualitätsfilter entfernt. Versuche die erweiterten Einstellungen anzupassen.")
                        st.session_state["sf_results_df"] = None
                    else:
                        # Build user prefs
                        hp = HOLDING_PERIOD_MAP[holding]
                        user_prefs = {
                            "goal": goal_option,
                            "min_locked_in_profit_pct": sf_min_profit_pct,
                            "target_dte": hp["target_dte"],
                            "holding_period": holding,
                        }

                        # Add month/label helpers
                        month_map = {
                            1: 'Januar', 2: 'Februar', 3: 'März', 4: 'April',
                            5: 'Mai', 6: 'Juni', 7: 'Juli', 8: 'August',
                            9: 'September', 10: 'Oktober', 11: 'November', 12: 'Dezember',
                        }
                        filtered_df['expiration_date'] = pd.to_datetime(filtered_df['expiration_date'])
                        filtered_df['exp_month_display'] = filtered_df['expiration_date'].apply(
                            lambda x: f"{x.strftime('%Y-%m')} ({month_map.get(x.month, '')})")
                        filtered_df['option_label'] = filtered_df.apply(
                            lambda r: (
                                f"{r['symbol']} {r['expiration_date'].year} "
                                f"{r['expiration_date'].strftime('%d-%b').upper()} "
                                f"{r['strike_price']:.2f} PUT ({int(r['days_to_expiration'])})"
                            ), axis=1)

                        scored_df = calculate_smart_scores(filtered_df, user_prefs, custom_weights)
                        st.session_state["sf_results_df"] = scored_df
                        st.rerun()

        except Exception as e:
            st.error(f"Fehler: {e}")
            logger.error(e, exc_info=True)
            st.session_state["sf_results_df"] = None

elif search_btn and not sf_symbol:
    st.warning("Bitte ein Aktiensymbol eingeben.")

# =====================================================================
# RESULTS
# =====================================================================
if st.session_state.get("sf_results_df") is not None:
    scored_df = st.session_state["sf_results_df"]
    stats = st.session_state.get("sf_filter_stats", {})
    current_price = scored_df['live_stock_price'].iloc[0] if not scored_df.empty else 0

    # ── Filter stats ────────────────────────────────────────────────
    total = stats.get("total", 0)
    removed = total - stats.get("remaining", total)
    remaining = stats.get("remaining", total)

    st.divider()
    fc1, fc2, fc3 = st.columns(3)
    fc1.metric("📊 Datenbasis", f"{total} Put-Optionen")
    fc2.metric("🗑️ Gefiltert", f"{removed} entfernt",
               f"OI=0: {stats.get('removed_oi_zero', 0)}, DTE<7: {stats.get('removed_dte', 0)}")
    fc3.metric("✅ Verbleibend", f"{remaining} Optionen")

    # ── Determine how many meet goal ────────────────────────────────
    meets_goal = scored_df[scored_df['locked_in_profit_pct'] >= sf_min_profit_pct]
    goal_label = {
        "lock_profit": f"≥ {sf_min_profit_pct:.0f}% Locked-in Profit",
        "limit_loss": f"Max. Verlust ≤ {abs(sf_min_profit_pct):.0f}%",
        "cheapest": "Günstigste Absicherung",
    }.get(goal_option, "")

    if meets_goal.empty and goal_option != "cheapest":
        best_available = scored_df['locked_in_profit_pct'].max() if not scored_df.empty else 0
        st.warning(
            f"⚠️ Kein Ergebnis erfüllt dein Ziel von **{goal_label}**. "
            f"Bestes verfügbares Ergebnis: **{best_available:.1f}%**. "
            f"Hier die Top-Optionen nach Gesamtbewertung."
        )
    else:
        n_goal = len(meets_goal) if goal_option != "cheapest" else remaining
        st.success(f"**{n_goal}** Optionen erfüllen dein Ziel ({goal_label}) – beste zuerst.")

    st.divider()

    # ── Top-3 Recommendations ───────────────────────────────────────
    user_prefs = {
        "goal": goal_option,
        "min_locked_in_profit_pct": sf_min_profit_pct,
    }
    recs = get_top_recommendations(scored_df, user_prefs)

    st.subheader("Top-Empfehlungen")
    rc1, rc2, rc3 = st.columns(3)

    cheapest = recs.get("cheapest")
    best_prot = recs.get("best_protection")
    best_bal = recs.get("best_balance")

    with rc1:
        st.markdown("### 🏆 Günstigste")
        if cheapest is not None:
            st.markdown(f"**{cheapest['option_label']}**")
            st.metric("Kosten p.a.", f"{cheapest['annualized_cost_pct']:.1f}%")
            st.metric("Locked-in Profit", f"{cheapest['locked_in_profit_pct']:.1f}%")
            st.caption(f"OI: {int(cheapest['open_interest'])} | Score: {cheapest['smart_score']}")
        else:
            st.info("Keine passende Option gefunden.")

    with rc2:
        st.markdown("### 🛡️ Bester Schutz")
        if best_prot is not None:
            st.markdown(f"**{best_prot['option_label']}**")
            st.metric("Locked-in Profit", f"{best_prot['locked_in_profit_pct']:.1f}%")
            st.metric("Absicherungstiefe", f"{best_prot['downside_protection_pct']:.1f}%")
            st.caption(f"OI: {int(best_prot['open_interest'])} | Score: {best_prot['smart_score']}")
        else:
            st.info("Keine passende Option gefunden.")

    with rc3:
        st.markdown("### ⚖️ Beste Balance")
        if best_bal is not None:
            st.markdown(f"**{best_bal['option_label']}**")
            st.metric("Smart Score", f"{best_bal['smart_score']}")
            st.metric("Kosten p.a.", f"{best_bal['annualized_cost_pct']:.1f}%")
            st.caption(
                f"Profit: {best_bal['locked_in_profit_pct']:.1f}% | "
                f"OI: {int(best_bal['open_interest'])}"
            )
        else:
            st.info("Keine passende Option gefunden.")

    # ── Insight text ────────────────────────────────────────────────
    if best_bal is not None and cheapest is not None:
        # Pick two different options for comparison
        top1 = best_bal
        top2 = cheapest if cheapest.name != best_bal.name else best_prot
        if top2 is not None:
            insight = generate_comparison_insight(top1, top2)
            if insight:
                st.markdown(insight)

    st.divider()

    # ── Comparison table ────────────────────────────────────────────
    top_n = st.session_state.get("sf_adv_topn", 15)
    display_df = scored_df.head(top_n).copy()

    smart_finder_cols = [
        'smart_score',
        'option_label',
        'option_price',
        'days_to_expiration',
        'annualized_cost_pct',
        'locked_in_profit',
        'locked_in_profit_pct',
        'time_value_per_month',
        'open_interest',
        'downside_protection_pct',
    ]
    # Only include columns that exist
    smart_finder_cols = [c for c in smart_finder_cols if c in display_df.columns]

    column_config = {
        "smart_score": st.column_config.NumberColumn("Score", format="%.1f", help="Smart Score (0-100)"),
        "option_label": st.column_config.TextColumn("Put (DTE)", width="large"),
        "option_price": st.column_config.NumberColumn("Put Preis", format="%.2f $"),
        "days_to_expiration": st.column_config.NumberColumn("DTE", format="%d"),
        "annualized_cost_pct": st.column_config.NumberColumn("Kosten p.a. (%)", format="%.2f %%"),
        "locked_in_profit": st.column_config.NumberColumn("Locked-in Profit ($)", format="%.2f $"),
        "locked_in_profit_pct": st.column_config.NumberColumn("Locked-in Profit (%)", format="%.2f %%"),
        "time_value_per_month": st.column_config.NumberColumn("Zeitwert/Monat", format="%.2f $"),
        "open_interest": st.column_config.NumberColumn("Open Interest"),
        "downside_protection_pct": st.column_config.NumberColumn("Absicherungstiefe (%)", format="%.2f %%"),
        "symbol": None,
        "live_stock_price": None,
        "stock_close": None,
        "contract_type": None,
        "exp_month_display": None,
    }

    st.subheader(f"Vergleichstabelle – Top {len(display_df)}")

    display_ordered = display_df[smart_finder_cols].copy()
    if 'symbol' not in display_ordered.columns:
        display_ordered['symbol'] = display_df['symbol']

    page_display_dataframe(display_ordered, page='smart_finder', symbol_column='symbol', column_config=column_config)

    # ── Full list expander ──────────────────────────────────────────
    if len(scored_df) > top_n:
        with st.expander(f"📋 Alle {len(scored_df)} Ergebnisse anzeigen", expanded=False):
            full_ordered = scored_df[smart_finder_cols].copy()
            if 'symbol' not in full_ordered.columns:
                full_ordered['symbol'] = scored_df['symbol']
            page_display_dataframe(full_ordered, page='smart_finder_full', symbol_column='symbol', column_config=column_config)
