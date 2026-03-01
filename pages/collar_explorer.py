import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.collar_explorer_engine import (
    calculate_explorer_columns,
    create_collar_scatter,
    find_sweet_spots,
    render_collar_detail
)

st.set_page_config(page_title="Collar Explorer", page_icon="📈", layout="wide")

st.title("📈 Collar Explorer")
st.caption("Visuelle Entscheidungshilfe für Collar-Optionen – Finde den optimalen Trade-off zwischen Schutz, Kosten und Upside.")

df = st.session_state.get('collar_combos_df')
current_price = st.session_state.get('collar_current_price')
cost_basis = st.session_state.get('collar_cost_basis')

if df is None or df.empty:
    st.info("""
    ### 👋 Willkommen im Collar Explorer!
    
    Der Collar Explorer visualisiert alle potenziellen Put+Call-Kombinationen (Collars) als interaktives Chart, 
    damit du den optimalen Trade-off zwischen Schutz, Kosten und Upside findest.
    
    **So startest du:**
    1. Öffne den **[Married Put Finder](/married_put_finder)**.
    2. Gib ein Aktiensymbol ein und klicke auf CALCULATE.
    3. Wähle **sowohl einen "Buy Put Month" als auch einen "Sell Call Month"** aus.
    4. Klicke auf den Button **"Zum Collar Explorer wechseln"**, der über der Tabelle erscheint.
    
    *Deine berechneten Daten werden dann direkt hierher übertragen.*
    """)
    st.stop()

# --- 2. Explorer-Spalten berechnen ---
df = calculate_explorer_columns(df, current_price)

# Metrics Banner
profit = current_price - cost_basis
profit_pct = (profit / cost_basis * 100) if cost_basis > 0 else 0
st.success(
    f"Current Price: **{current_price:.2f}$** &ensp;|&ensp; "
    f"Your Cost Basis: **{cost_basis:.2f}$** &ensp;|&ensp; "
    f"Unrealized Profit: **{profit:+.2f}$ ({profit_pct:+.1f}%)**"
)

# --- 3. Anleitung ---
with st.expander("💡 Wie liest du den Chart?", expanded=False):
    st.markdown("""
    Jeder Punkt ist eine Put+Call-Kombination.
    
    - **X-Achse** & **Y-Achse**: Wähle die Metriken, die dir am wichtigsten sind (z.B. Kosten vs. Absicherung).
    - **Farbe**: Jeder Put-Strike hat seine eigene Farbe.
    - **Hover**: Fahre mit der Maus über einen Punkt, um die Kernwerte zu sehen.
    - **Klick**: Klicke auf einen Punkt, um unten die vollständige Detail-Berechnung anzuzeigen.
    - Es gibt nicht _die beste_ Kombination – es geht um deinen persönlichen Trade-off!
    """)

# --- 4. Filter & Achsen-Auswahl ---
col_x, col_y, col_put, col_lip = st.columns([2, 2, 2, 2])

AXIS_OPTIONS = {
    'net_cost':         'Netto-Kosten ($)',
    'locked_in_profit_pct': 'Locked-in Profit (%)',
    'max_profit_pct':   'Max. Gewinn bei Assignment (%)',
    'upside_room_pct':  'Upside bis Assignment (%)',
    'new_cost_basis':   'Neuer Einstandskurs ($)',
    'insurance_net_pct':'Netto-Versicherung (% vom Kurs)',
}

AXIS_BETTER = {
    'net_cost': 'low',
    'locked_in_profit_pct': 'high',
    'max_profit_pct': 'high',
    'upside_room_pct': 'high',
    'new_cost_basis': 'low',
    'insurance_net_pct': 'low',
}

with col_x:
    x_axis = st.selectbox("X-Achse", options=list(AXIS_OPTIONS.keys()),
                           format_func=lambda k: AXIS_OPTIONS[k],
                           index=0, key='ce_x_axis')

with col_y:
    y_axis = st.selectbox("Y-Achse", options=list(AXIS_OPTIONS.keys()),
                           format_func=lambda k: AXIS_OPTIONS[k],
                           index=1, key='ce_y_axis')

with col_put:
    put_strikes = ['Alle'] + sorted(df['put_strike'].unique().tolist())
    put_filter = st.selectbox("Put Strike Filter", options=put_strikes, index=0, key='ce_put_filter')

with col_lip:
    min_lip = st.slider("Min. Locked-in Profit (%)",
                         min_value=-100, max_value=200, value=0, step=10,
                         key='ce_min_lip')

# --- 5. Filter anwenden ---
filtered_df = df.copy()
if put_filter != 'Alle':
    filtered_df = filtered_df[filtered_df['put_strike'] == put_filter]
filtered_df = filtered_df[filtered_df['locked_in_profit_pct'] >= min_lip]

st.caption(f"{len(filtered_df)} von {len(df)} Kombinationen angezeigt")

if filtered_df.empty:
    st.info("Keine Kombinationen mit den aktuellen Filtern gefunden.")
    st.stop()

# --- 6. Sweet Spots berechnen ---
sweet_spots = find_sweet_spots(filtered_df)

# --- 7. Layout: Chart (links) + Detail (rechts) ---
col_chart, col_detail = st.columns([2, 1])

selected_point = None

with col_chart:
    fig = create_collar_scatter(
        filtered_df, x_axis, y_axis, 
        AXIS_OPTIONS[x_axis], AXIS_OPTIONS[y_axis], 
        AXIS_BETTER[x_axis], AXIS_BETTER[y_axis]
    )
    
    # Sweet Spots als Annos im Chart
    for key, spot in sweet_spots.items():
        if spot is not None and not spot.empty:
            fig.add_trace(go.Scatter(
                x=[spot[x_axis]],
                y=[spot[y_axis]],
                mode='markers',
                marker=dict(
                    size=24,
                    color='rgba(0,0,0,0)',
                    line=dict(width=2, color='white', dash='dash')
                ),
                showlegend=False,
                hoverinfo='skip'
            ))
            
    event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="ce_scatter")

with col_detail:
    st.subheader("Sweet Spots")
    SPOT_CONFIG = [
        ('cheapest',        '💰', 'Günstigste',          'net_cost',             lambda v: f"{v:.2f}$"),
        ('best_protection', '🛡️', 'Meiste Absicherung',  'locked_in_profit_pct', lambda v: f"{v:.0f}%"),
        ('best_balance',    '⚖️', 'Beste Balance',        'locked_in_profit_pct', lambda v: f"{v:.0f}%"),
        ('most_upside',     '🚀', 'Meistes Upside',       'upside_room_pct',      lambda v: f"+{v:.0f}%"),
    ]
    
    for key, icon, label, metric_col, formatter in SPOT_CONFIG:
        spot = sweet_spots.get(key)
        if spot is None or spot.empty:
            continue
        
        value_str = formatter(spot[metric_col])
        if st.button(
            f"{icon} {label}: Put {spot['put_strike']:.2f}$ + Call {spot['call_strike']:.2f}$ → {value_str}",
            key=f"sweet_{key}",
            use_container_width=True,
        ):
            selected_point = spot
            
    # Chart-Click Event prüfen (überschreibt Button-Click falls es einen neuen gibt)
    if event and hasattr(event, "selection") and event.selection and event.selection.get("points"):
        idx = event.selection["points"][0]["point_index"]
        selected_point = filtered_df.iloc[idx]
        
    st.divider()
    
    if selected_point is not None:
        render_collar_detail(selected_point, current_price, cost_basis)
    else:
        st.markdown(
            "<div style='text-align:center; padding:30px; color:#5a6e87;'>"
            "👆<br>Klicke einen Punkt im Chart oder eine Empfehlung<br>"
            "für die vollständige Berechnung"
            "</div>",
            unsafe_allow_html=True
        )

# --- 8. Trade-off-Erklärung (Footer) ---
st.divider()
st.markdown("### Das Trade-off-Dreieck")

t1, t2, t3 = st.columns(3)

with t1:
    st.markdown("""
    **🛡️ Mehr Schutz**
    
    Höherer Put-Strike → mehr Locked-in Profit. 
    Aber: Put kostet meist mehr.
    """)

with t2:
    st.markdown("""
    **💰 Weniger Kosten**
    
    Niedrigerer Call-Strike → mehr Prämie.
    Aber: Aktie wird früher abgerufen, weniger Upside möglich.
    """)

with t3:
    st.markdown("""
    **🚀 Mehr Upside**
    
    Höherer Call-Strike → Aktie kann weiter steigen.
    Aber: Weniger Call-Prämie zur Gegenfinanzierung.
    """)

st.info(
    "**Faustregel:** Du kannst immer nur 2 von 3 optimieren. "
    "Willst du maximalen Schutz UND maximales Upside, wird es teuer. "
    "Willst du es günstig UND viel Upside, bekommst du weniger Schutz. "
    "Es gibt keinen Free Lunch – aber es gibt einen **Sweet Spot**, der zu deiner Situation passt."
)
