import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

def calculate_explorer_columns(df: pd.DataFrame, current_price: float) -> pd.DataFrame:
    df = df.copy()
    
    # Fülle NaN bei call_price und call_strike mit 0 für Put-Only
    df['call_price'] = df['call_price'].fillna(0)
    df['call_strike'] = df['call_strike'].fillna(0)
    
    df['net_cost'] = df['put_price'] - df['call_price']
    df['max_profit'] = df['call_strike'] - df['new_cost_basis']
    df['max_profit_pct'] = (df['max_profit'] / df['new_cost_basis']) * 100
    df['upside_room_pct'] = ((df['call_strike'] - current_price) / current_price) * 100
    df['insurance_net_pct'] = (df['net_cost'] / current_price) * 100
    
    # Für Hover und Kategorien
    def build_hover(r):
        if r['call_strike'] > 0:
            title = f"<b>Put {r['put_strike']:.2f}$ + Call {r['call_strike']:.2f}$</b><br>"
            stats = f"Max Gewinn: {r['max_profit_pct']:.1f}% | Upside: {r['upside_room_pct']:.1f}%<br>"
        else:
            title = f"<b>Put {r['put_strike']:.2f}$ (Kein Call)</b><br>"
            stats = "Max Gewinn: Unbegrenzt | Upside: Unbegrenzt<br>"
            
        return (
            title +
            f"Netto: {r['net_cost']:.2f}$ | LiP: {r['locked_in_profit_pct']:.1f}%<br>" +
            stats +
            f"Einstand: {r['new_cost_basis']:.2f}$"
        )
        
    df['hover_text'] = df.apply(build_hover, axis=1)
    
    df['put_strike_label'] = df['put_strike'].apply(lambda x: f"{x:.2f}$ Put")
    
    return df

def find_sweet_spots(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    
    cheapest = df.loc[df['net_cost'].idxmin()]
    best_protection = df.loc[df['locked_in_profit_pct'].idxmax()]
    
    upside_candidates = df[df['locked_in_profit'] > 0]
    if not upside_candidates.empty:
        most_upside = upside_candidates.loc[upside_candidates['upside_room_pct'].idxmax()]
    else:
        most_upside = df.loc[df['upside_room_pct'].idxmax()]
    
    sorted_by_cost = df.sort_values('net_cost')
    cheap_half = sorted_by_cost.head(max(1, len(sorted_by_cost) // 2))
    best_balance = cheap_half.loc[cheap_half['locked_in_profit_pct'].idxmax()]
    
    return {
        'cheapest': cheapest,
        'best_protection': best_protection,
        'most_upside': most_upside,
        'best_balance': best_balance,
    }

def create_collar_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    x_label: str,
    y_label: str,
    x_better: str,
    y_better: str,
) -> go.Figure:
    
    # Dynamische Farbpalette auf Basis der vorhandenen Put Strikes
    color_discrete_sequence = px.colors.qualitative.Plotly
    
    fig = px.scatter(
        df,
        x=x_col,
        y=y_col,
        color='put_strike_label',
        color_discrete_sequence=color_discrete_sequence,
        hover_name='hover_text',
        custom_data=['put_strike', 'call_strike', 'net_cost', 
                     'locked_in_profit_pct', 'max_profit_pct', 
                     'upside_room_pct', 'new_cost_basis',
                     'put_price', 'call_price', 'locked_in_profit'],
    )
    
    x_arrow = "← besser" if x_better == "low" else "besser →"
    y_arrow = "besser ↑" if y_better == "high" else "↑ besser"
    
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor='#0e1117',
        plot_bgcolor='#0e1117',
        font=dict(family="monospace", size=12, color='#c8d6e5'),
        xaxis_title=f"{x_label}  ({x_arrow})",
        yaxis_title=f"({y_arrow})  {y_label}",
        legend_title="Put Strike",
        height=500,
        margin=dict(l=60, r=30, t=30, b=60),
        xaxis=dict(gridcolor='#1e2d4a', gridwidth=0.5),
        yaxis=dict(gridcolor='#1e2d4a', gridwidth=0.5),
    )
    
    fig.update_traces(
        marker=dict(size=12, opacity=0.8, line=dict(width=1, color='#1e2d4a')),
    )
    
    return fig

def render_collar_detail(row: pd.Series, current_price: float, cost_basis: float):
    put_strike = row['put_strike']
    call_strike = row['call_strike']
    put_price = row['put_price']
    call_price = row['call_price']
    net_cost = put_price - call_price
    ncb = row['new_cost_basis']
    lip = row['locked_in_profit']
    lip_pct = row['locked_in_profit_pct']
    max_profit = call_strike - ncb
    max_profit_pct = (max_profit / ncb) * 100 if ncb != 0 else 0
    upside = ((call_strike - current_price) / current_price) * 100 if current_price != 0 else 0
    
    st.markdown(f"### Put {put_strike:.2f}$ + Call {call_strike:.2f}$")
    
    st.markdown(f'''
| Schritt | Betrag |
|---|---|
| Put kaufen | **-{put_price:.2f}$** |
| Call verkaufen | **+{call_price:.2f}$** |
| **Netto-Kosten** | **{net_cost:.2f}$** {'(Credit!)' if net_cost <= 0 else '(Debit)'} |
''')
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Neuer Einstand", f"{ncb:.2f}$",
              delta=f"{ncb - cost_basis:+.2f}$ vs. Einstand",
              delta_color="inverse")
    c2.metric("Locked-in Profit", f"{lip:.2f}$ ({lip_pct:.1f}%)",
              delta="Garantiert" if lip > 0 else "Verlustrisiko",
              delta_color="normal" if lip > 0 else "inverse")
    if call_strike > 0:
        c3.metric("Max. Gewinn", f"{max_profit:.2f}$ ({max_profit_pct:.1f}%)",
                  delta=f"bei {call_strike:.2f}$ (Assignment)")
    else:
        c3.metric("Max. Gewinn", "Unbegrenzt", delta="Kein Call verkauft")
    
    with st.expander("📖 Berechnung im Detail", expanded=False):
        if call_strike > 0:
            max_profit_str = f"{max_profit:.2f}$ ({max_profit_pct:.1f}%)"
            call_form_str = f"- {call_price:.2f}"
            assignment_str = f"""
**Max. Gewinn bei Assignment:**
= Call Strike - Neuer Einstand
= {call_strike:.2f} - {ncb:.2f}
= {max_profit_str}
"""
        else:
            max_profit_str = "Unbegrenzt"
            call_form_str = ""
            assignment_str = ""

        st.markdown(f"""
**Neuer Einstandskurs:**
= Einstand + Put - Call
= {cost_basis:.2f} + {put_price:.2f} {call_form_str}
= {ncb:.2f}$

**Locked-in Profit (garantierter Mindestgewinn):**
= Put Strike - Neuer Einstand
= {put_strike:.2f} - {ncb:.2f}
= {lip:.2f}$ ({lip_pct:.1f}%)
{assignment_str}
""")
    
    if net_cost <= 0:
        cost_text = f"Die Absicherung kostet dich **nichts** – du bekommst sogar **{abs(net_cost):.2f}$ Credit**."
    else:
        cost_text = f"Die Absicherung kostet dich netto **{net_cost:.2f}$** pro Aktie."
    
    if call_strike > 0:
        if call_strike > current_price:
            upside_text = f"Die Aktie kann noch bis **{call_strike:.2f}$** steigen (+{upside:.1f}%), bevor sie abgerufen wird."
        else:
            upside_text = f"⚠️ **Achtung:** Call-Strike ({call_strike:.2f}$) liegt unter dem aktuellen Kurs ({current_price:.2f}$) – sofortiges Assignment-Risiko!"
        profit_range = f"Deine Gewinnspanne liegt zwischen **{lip:.2f}$** (Aktie crasht) und **{max_profit:.2f}$** (Assignment bei {call_strike:.2f}$)."
    else:
        upside_text = "Die Aktie kann **unbegrenzt** weiter steigen, da kein Call verkauft wurde."
        profit_range = f"Dein Risiko ist nach unten auf **{lip:.2f}$** begrenzt, nach oben hast du unbegrenztes Gewinnpotenzial."
    
    st.info(f"""
**Was bedeutet das?**

Egal was passiert, du behältst mindestens **{lip:.2f}$ Gewinn** pro Aktie ({lip_pct:.1f}%).
{cost_text}
{upside_text}

{profit_range}
""")
