"""Covered Call Screener - PowerOptions Style.

ITM Covered Calls mit Berechnung von Assigned Return, Annualized Return,
Downside Protection und Net Debit. Filtert nach Liquidität, Earnings und Technik.
Includes all PowerOptions filtering criteria from their YouTube methodology.
"""

import logging
import os
import streamlit as st
import pandas as pd
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.covered_call_calculation import calc_covered_calls, get_page_covered_calls
from src.ui_utils import init_session_state, reset_to_defaults as ui_reset, filter_by_expiration_type
from src.utils.option_utils import get_expiration_type

# Ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

# Setup logging
setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start Page: {os.path.basename(__file__)}")

# Constants for default values
DEFAULT_SHOW_MONTHLY = True
DEFAULT_SHOW_WEEKLY = False
DEFAULT_SHOW_DAILY = False
DEFAULT_DELTA_TARGET = 0.6
DEFAULT_MIN_OPEN_INTEREST = 100
DEFAULT_MIN_VOLUME = 10
DEFAULT_MAX_PER_SYMBOL = 3
DEFAULT_MIN_ANNUALIZED = 0.10
DEFAULT_MIN_DOWNSIDE = 0.02
DEFAULT_EARNINGS_FILTER = True
DEFAULT_ABOVE_MA20 = False
DEFAULT_ABOVE_MA50 = False
# PowerOptions defaults
DEFAULT_MACD_POSITIVE = True
DEFAULT_RSI_BELOW_70 = True
DEFAULT_MIN_EPS_GROWTH = 5.0
DEFAULT_MAX_PE_RATIO = 50.0
DEFAULT_MAX_RECOMMENDATION = 2.6
DEFAULT_MIN_AVG_VOLUME = 500000
DEFAULT_MIN_MARKET_CAP = 2500.0
DEFAULT_EXCLUDE_BIOTECH = True
DEFAULT_EXCLUDE_LEVERAGED = True
DEFAULT_MAX_IV_HV_RATIO = 0.0  # 0 = disabled

# Page header
st.title("Covered Calls")
st.caption("PowerOptions-Style ITM Covered Call Screener")

# Default values mapping for UI utils
DEFAULTS = {
    'cc_show_monthly': DEFAULT_SHOW_MONTHLY,
    'cc_show_weekly': DEFAULT_SHOW_WEEKLY,
    'cc_show_daily': DEFAULT_SHOW_DAILY,
    'cc_delta_target': DEFAULT_DELTA_TARGET,
    'cc_min_open_interest': DEFAULT_MIN_OPEN_INTEREST,
    'cc_min_volume': DEFAULT_MIN_VOLUME,
    'cc_max_per_symbol': DEFAULT_MAX_PER_SYMBOL,
    'cc_min_annualized': DEFAULT_MIN_ANNUALIZED,
    'cc_min_downside': DEFAULT_MIN_DOWNSIDE,
    'cc_earnings_filter': DEFAULT_EARNINGS_FILTER,
    'cc_above_ma20': DEFAULT_ABOVE_MA20,
    'cc_above_ma50': DEFAULT_ABOVE_MA50,
    # PowerOptions
    'cc_macd_positive': DEFAULT_MACD_POSITIVE,
    'cc_rsi_below_70': DEFAULT_RSI_BELOW_70,
    'cc_min_eps_growth': DEFAULT_MIN_EPS_GROWTH,
    'cc_max_pe_ratio': DEFAULT_MAX_PE_RATIO,
    'cc_max_recommendation': DEFAULT_MAX_RECOMMENDATION,
    'cc_min_avg_volume': DEFAULT_MIN_AVG_VOLUME,
    'cc_min_market_cap': DEFAULT_MIN_MARKET_CAP,
    'cc_exclude_biotech': DEFAULT_EXCLUDE_BIOTECH,
    'cc_exclude_leveraged': DEFAULT_EXCLUDE_LEVERAGED,
    'cc_max_iv_hv_ratio': DEFAULT_MAX_IV_HV_RATIO,
}

init_session_state(DEFAULTS)


def reset_to_defaults():
    ui_reset(DEFAULTS)


# Filter with expander section
with st.expander("Configuration and Filters", expanded=True):
    st.button("Reset to Defaults", on_click=reset_to_defaults)

    # First row: Expiration + Delta Target + Max per Symbol + Min OI
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Load expiration dates
        sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'expiration_dte_asc.sql'
        dates_df = select_into_dataframe(sql_file_path=sql_file_path)

        # Filter dates_df based on checkbox states
        filtered_dates_df = filter_by_expiration_type(
            dates_df,
            'expiration_date',
            st.session_state.cc_show_monthly,
            st.session_state.cc_show_weekly,
            st.session_state.cc_show_daily
        )

        # DTE labels
        dte_labels = [
            (
                f"{int(row['days_to_expiration'])} DTE - "
                f"{pd.to_datetime(row['expiration_date']).strftime('%A')}  "
                f"{row['expiration_date']} - "
                f"{get_expiration_type(row['expiration_date'])}"
            )
            for _, row in filtered_dates_df.iterrows()
        ]

        if not dte_labels:
            st.warning("No expiration dates match the selected filters.")
            st.stop()

        selected_label = st.selectbox("Expiration Date", dte_labels, index=min(1, len(dte_labels) - 1))
        selected_index = dte_labels.index(selected_label)
        expiration_date = filtered_dates_df.iloc[selected_index]['expiration_date']

    with col2:
        delta_target = st.number_input(
            "Delta Target (ITM)",
            min_value=0.3,
            max_value=0.95,
            step=0.05,
            key="cc_delta_target",
            help="Target delta for ITM calls. Higher = deeper ITM, more protection."
        )

    with col3:
        max_per_symbol = st.number_input(
            "Max per Symbol",
            min_value=1,
            max_value=10,
            step=1,
            key="cc_max_per_symbol",
            help="Maximum number of strikes per symbol (ranked by delta proximity)."
        )

    with col4:
        min_open_interest = st.number_input(
            "Min Open Interest",
            min_value=0,
            step=50,
            key="cc_min_open_interest"
        )

    # Second row: Return filters + Volume
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        min_annualized = st.slider(
            "Min Annualized Return %",
            min_value=0,
            max_value=100,
            step=1,
            value=int(st.session_state.cc_min_annualized * 100),
            key="cc_min_annualized_slider",
            help="Minimum annualized return if assigned."
        ) / 100.0

    with col6:
        min_downside = st.slider(
            "Min Downside Protection %",
            min_value=0,
            max_value=30,
            step=1,
            value=int(st.session_state.cc_min_downside * 100),
            key="cc_min_downside_slider",
            help="Minimum premium as % of stock price (protection buffer)."
        ) / 100.0

    with col7:
        min_volume = st.number_input(
            "Min Volume",
            min_value=0,
            step=5,
            key="cc_min_volume"
        )

    with col8:
        st.checkbox("Show Monthly", key="cc_show_monthly")
        st.checkbox("Show Weekly", key="cc_show_weekly")
        st.checkbox("Show Daily", key="cc_show_daily")

    # Third row: Technical Toggles
    col9, col10, col11, col12 = st.columns(4)

    with col9:
        earnings_filter = st.checkbox(
            "Exclude Earnings before Exp",
            key="cc_earnings_filter",
            help="Remove stocks with earnings date before option expiration."
        )

    with col10:
        above_ma20 = st.checkbox(
            "Stock above 20-Day MA",
            key="cc_above_ma20",
            help="Only show stocks trading above their 20-day moving average."
        )

    with col11:
        above_ma50 = st.checkbox(
            "Stock above 50-Day MA",
            key="cc_above_ma50",
            help="Only show stocks trading above their 50-day moving average."
        )

    with col12:
        macd_positive = st.checkbox(
            "MACD Positive Crossover",
            key="cc_macd_positive",
            help="MACD above signal line, both positive (bullish momentum)."
        )

# PowerOptions Pro Filters
with st.expander("PowerOptions Pro Filters", expanded=False):
    st.caption("Professional filtering criteria from PowerOptions methodology")

    po_col1, po_col2, po_col3, po_col4 = st.columns(4)

    with po_col1:
        rsi_below_70 = st.checkbox(
            "RSI < 70 (not overbought)",
            key="cc_rsi_below_70",
            help="Exclude overbought stocks (RSI above 70)."
        )
        exclude_biotech = st.checkbox(
            "Exclude Biotech",
            key="cc_exclude_biotech",
            help="Biotech stocks are too volatile for covered calls."
        )
        exclude_leveraged = st.checkbox(
            "Exclude Leveraged ETFs",
            key="cc_exclude_leveraged",
            help="Leveraged/inverse ETFs have decay risk."
        )

    with po_col2:
        min_eps_growth = st.number_input(
            "Min EPS Growth %",
            min_value=0.0,
            max_value=100.0,
            step=1.0,
            key="cc_min_eps_growth",
            help="Minimum Forward EPS Growth (0 = disabled). PowerOptions uses > 5%."
        )
        max_pe_ratio = st.number_input(
            "Max P/E Ratio",
            min_value=0.0,
            max_value=200.0,
            step=5.0,
            key="cc_max_pe_ratio",
            help="Maximum trailing P/E ratio (0 = disabled). PowerOptions uses 50."
        )

    with po_col3:
        max_recommendation = st.number_input(
            "Max Analyst Rec (1-5)",
            min_value=0.0,
            max_value=5.0,
            step=0.1,
            key="cc_max_recommendation",
            help="Max analyst recommendation (1=Strong Buy, 5=Sell). PowerOptions uses 2.6."
        )
        min_avg_volume = st.number_input(
            "Min Avg Daily Volume",
            min_value=0,
            step=100000,
            key="cc_min_avg_volume",
            help="Minimum average daily volume (0 = disabled). PowerOptions uses 500k."
        )

    with po_col4:
        min_market_cap = st.number_input(
            "Min Market Cap ($M)",
            min_value=0.0,
            step=500.0,
            key="cc_min_market_cap",
            help="Minimum market cap in millions (0 = disabled). PowerOptions uses 2500M."
        )
        max_iv_hv_ratio = st.number_input(
            "Max IV/HV Ratio",
            min_value=0.0,
            max_value=5.0,
            step=0.1,
            key="cc_max_iv_hv_ratio",
            help="Max implied/historical volatility ratio (0 = disabled). High ratio = overpriced risk."
        )


@st.cache_data
def _cached_query(sql_file_path, params):
    return select_into_dataframe(sql_file_path=sql_file_path, params=params)


@st.cache_data
def _cached_calc(df):
    return calc_covered_calls(df)


# Query and calculate
with st.spinner("Searching for covered call opportunities..."):
    params = {
        "expiration_date": expiration_date,
        "min_open_interest": min_open_interest,
        "max_per_symbol": max_per_symbol,
        "delta_target": delta_target,
    }

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'covered_calls.sql'
    df = _cached_query(sql_file_path=sql_file_path, params=params)
    logger.debug(f"Raw query returned {len(df)} rows")

    if df.empty:
        st.warning("No ITM calls found for selected expiration. Try a different date.")
        st.stop()

    # Calculate metrics
    cc_df = _cached_calc(df)
    logger.debug(f"After calculation: {len(cc_df)} rows")

# Apply display filters (including PowerOptions)
filtered_df = get_page_covered_calls(
    cc_df,
    min_annualized=min_annualized,
    min_downside=min_downside,
    earnings_buffer_days=7 if earnings_filter else -9999,
    above_ma20=above_ma20,
    above_ma50=above_ma50,
    min_volume=min_volume,
    # PowerOptions
    macd_positive=macd_positive,
    rsi_below_70=rsi_below_70,
    min_eps_growth=min_eps_growth if min_eps_growth > 0 else None,
    max_pe_ratio=max_pe_ratio if max_pe_ratio > 0 else None,
    max_recommendation=max_recommendation if max_recommendation > 0 else None,
    min_avg_volume=int(min_avg_volume) if min_avg_volume > 0 else None,
    min_market_cap=min_market_cap if min_market_cap > 0 else None,
    exclude_biotech=exclude_biotech,
    exclude_leveraged=exclude_leveraged,
    max_iv_hv_ratio=max_iv_hv_ratio if max_iv_hv_ratio > 0 else None,
)

st.markdown(f"### {len(filtered_df)} Results")

if filtered_df.empty:
    st.info("No results match the current filters. Try reducing Min Annualized Return or disabling some PowerOptions filters.")
    st.stop()

# Display table
event = page_display_dataframe(
    filtered_df,
    page=None,  # Uses default Claude prompt (generic analysis)
    symbol_column='symbol',
    on_select="rerun",
    selection_mode="single-row"
)

# Detail Panel
if not filtered_df.empty:
    selected_rows = event.selection.rows if hasattr(event, "selection") else []
    if selected_rows:
        selected_idx = selected_rows[0]
        row = filtered_df.iloc[selected_idx]

        st.divider()
        st.markdown(f"### {row['symbol']} - {row.get('Company', 'N/A')}")

        # === TRADE ACTION SUMMARY ===
        exp_date = row.get('expiration_date', 'N/A')
        if pd.notnull(exp_date):
            exp_str = pd.Timestamp(exp_date).strftime('%Y-%m-%d') if not isinstance(exp_date, str) else str(exp_date)[:10]
        else:
            exp_str = 'N/A'

        st.markdown(f"""
<div style="background: linear-gradient(135deg, #1a3a2a 0%, #0d1f17 100%); border: 1px solid #22c55e40; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
<p style="color: #9ca3af; margin: 0 0 4px 0; font-size: 12px; text-transform: uppercase; letter-spacing: 1px;">Trade Action</p>
<p style="color: #22c55e; margin: 0; font-size: 20px; font-weight: bold;">
BUY 100x {row['symbol']} @ {row['Stock']} &nbsp;|&nbsp; SELL 1x {row['symbol']} {row['Strike']} Call @ {row['Premium']}
</p>
<p style="color: #d1d5db; margin: 4px 0 0 0; font-size: 14px;">
Expiration: {exp_str} ({row['DTE']:.0f} DTE) &nbsp;|&nbsp; Max Profit: {row.get('Max Profit', 'N/A')} &nbsp;|&nbsp; Protection: {row['Protection %']:.1f}%
</p>
</div>
        """, unsafe_allow_html=True)

        # Key metrics
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Stock Price", f"${row['Stock']:.2f}")
            st.metric("Strike", f"${row['Strike']:.2f}")
        with col_m2:
            st.metric("Premium", f"${row['Premium']:.2f}")
            st.metric("Net Debit", f"${row['Net Debit']:.2f}")
        with col_m3:
            st.metric("Assigned Return", f"{row['Assigned %']:.1f}%")
            st.metric("Annualized Return", f"{row['Annual %']:.1f}%")
        with col_m4:
            st.metric("Downside Protection", f"{row['Protection %']:.1f}%")
            st.metric("ITM Depth", f"{row['ITM %']:.1f}%")

        # Investment per contract (100 shares)
        st.markdown("#### Per Contract (100 Shares)")
        col_inv1, col_inv2, col_inv3, col_inv4 = st.columns(4)
        with col_inv1:
            st.metric("Investment (100 x Stock)", f"${row.get('Investment', 0):,.0f}")
        with col_inv2:
            st.metric("Premium Income", f"${row.get('Prem Income', 0):,.0f}")
        with col_inv3:
            st.metric("Net Cost (after Premium)", f"${row.get('Net Cost', 0):,.0f}")
        with col_inv4:
            st.metric("Max Profit (if assigned)", f"${row.get('Max Profit', 0):,.0f}")

        # Explain Button - shows concrete calculation
        if st.button("Explain Calculation", key="cc_explain_btn"):
            st.session_state['cc_show_explain'] = not st.session_state.get('cc_show_explain', False)

        if st.session_state.get('cc_show_explain', False):
            stock = row['Stock']
            strike = row['Strike']
            premium = row['Premium']
            net_debit = row['Net Debit']
            assigned_pct = row['Assigned %']
            annual_pct = row['Annual %']
            protection_pct = row['Protection %']
            itm_pct = row['ITM %']
            dte = row['DTE']

            st.markdown("---")
            st.markdown("#### Berechnungsdetails")
            st.markdown(f"""
**Net Debit** (effektiver Einstiegspreis pro Aktie):
> Stock Price - Premium = ${stock:.2f} - ${premium:.2f} = **${net_debit:.2f}**

**Assigned Return** (Rendite wenn Call ausgeuebt wird):
> (Strike + Premium - Stock Price) / Net Debit
> (${strike:.2f} + ${premium:.2f} - ${stock:.2f}) / ${net_debit:.2f}
> = ${strike + premium - stock:.2f} / ${net_debit:.2f} = **{assigned_pct:.1f}%**

**Annualized Return** (auf 365 Tage hochgerechnet):
> Assigned Return x (365 / DTE)
> {assigned_pct:.1f}% x (365 / {dte:.0f})
> = {assigned_pct:.1f}% x {365/dte:.2f} = **{annual_pct:.1f}%**

**Downside Protection** (Praemie als Puffer):
> Premium / Stock Price
> ${premium:.2f} / ${stock:.2f} = **{protection_pct:.1f}%**

**ITM Depth** (wie tief im Geld):
> (Stock Price - Strike) / Stock Price
> (${stock:.2f} - ${strike:.2f}) / ${stock:.2f}
> = ${stock - strike:.2f} / ${stock:.2f} = **{itm_pct:.1f}%**

**Per Contract (100 Shares):**
> Investment = 100 x ${stock:.2f} = **${stock * 100:,.0f}**
> Premium Income = 100 x ${premium:.2f} = **${premium * 100:,.0f}**
> Net Cost = 100 x ${net_debit:.2f} = **${net_debit * 100:,.0f}**
> Max Profit = 100 x (Strike - Stock + Premium) = 100 x (${strike:.2f} - ${stock:.2f} + ${premium:.2f}) = **${(strike - stock + premium) * 100:,.0f}**
            """)
            st.markdown("---")

        # PowerOptions indicators
        st.markdown("#### Technical & Fundamental")
        col_t1, col_t2, col_t3, col_t4 = st.columns(4)
        with col_t1:
            st.write(f"**Delta:** {row['delta']}")
            st.write(f"**IV:** {row['iv']}" if row.get('iv') else "**IV:** N/A")
            iv_hv = row.get('IV/HV')
            st.write(f"**IV/HV Ratio:** {iv_hv}" if iv_hv else "**IV/HV Ratio:** N/A")
        with col_t2:
            st.write(f"**Open Interest:** {row['OI']}")
            st.write(f"**Volume:** {row['Vol']}")
            avg_vol = row.get('Avg Vol')
            st.write(f"**Avg Volume:** {avg_vol}" if avg_vol else "**Avg Volume:** N/A")
        with col_t3:
            macd_val = row.get('MACD')
            macd_sig = row.get('MACD Signal')
            rsi_val = row.get('RSI')
            st.write(f"**MACD:** {macd_val}" if macd_val else "**MACD:** N/A")
            st.write(f"**MACD Signal:** {macd_sig}" if macd_sig else "**MACD Signal:** N/A")
            st.write(f"**RSI(14):** {rsi_val}" if rsi_val else "**RSI(14):** N/A")
        with col_t4:
            eps = row.get('EPS Growth %')
            pe = row.get('P/E')
            rec = row.get('Rec')
            mkt_cap = row.get('Mkt Cap')
            st.write(f"**EPS Growth:** {eps}" if eps else "**EPS Growth:** N/A")
            st.write(f"**P/E Ratio:** {pe}" if pe else "**P/E Ratio:** N/A")
            st.write(f"**Analyst Rec:** {rec}" if rec else "**Analyst Rec:** N/A")
            st.write(f"**Market Cap:** {mkt_cap}" if mkt_cap else "**Market Cap:** N/A")

        # Additional info
        col_i1, col_i2, col_i3 = st.columns(3)
        with col_i1:
            sector = row.get('company_sector', 'N/A')
            industry = row.get('company_industry', 'N/A')
            st.write(f"**Sector:** {sector}")
            st.write(f"**Industry:** {industry}")
        with col_i2:
            earnings = row.get('earnings_date_next')
            if pd.notnull(earnings):
                st.write(f"**Next Earnings:** {earnings}")
            else:
                st.write("**Next Earnings:** N/A")
        with col_i3:
            pass

        # Links
        st.markdown("#### Links")
        link_col1, link_col2, link_col3, link_col4 = st.columns(4)
        with link_col1:
            st.link_button("TradingView", f"https://www.tradingview.com/symbols/{row['symbol']}/", use_container_width=True)
        with link_col2:
            st.link_button("Chart", f"https://www.tradingview.com/chart/?symbol={row['symbol']}", use_container_width=True)
        with link_col3:
            st.link_button("Yahoo Finance", f"https://finance.yahoo.com/quote/{row['symbol']}", use_container_width=True)
        with link_col4:
            if 'Claude' in row and pd.notnull(row.get('Claude')):
                st.link_button("Claude AI", row['Claude'], use_container_width=True)

    else:
        st.caption("Klicke auf eine Zeile, um Details zu sehen.")

# Footer info
st.divider()
with st.expander("PowerOptions Methodik", expanded=False):
    st.markdown("""
**Covered Call (Buy-Write):** Aktie kaufen + ITM Call verkaufen.

**Kennzahlen:**
- **Net Debit** = Aktienkurs - Premium (effektiver Einstiegspreis)
- **Assigned Return** = (Strike + Premium - Aktienkurs) / Net Debit (Rendite bei Ausuebung)
- **Annualized Return** = Assigned Return x (365 / DTE) (auf ein Jahr hochgerechnet)
- **Downside Protection** = Premium / Aktienkurs (Puffer nach unten in %)
- **ITM Depth** = (Aktienkurs - Strike) / Aktienkurs (wie tief im Geld)

**PowerOptions Pro-Filter:**
- MACD ueber Signal-Linie, beide positiv (Momentum-Bestaetigung)
- RSI < 70 (nicht ueberkauft)
- EPS Growth > 5% (Fundamental-Qualitaet)
- P/E Ratio 0-50 (Bewertungs-Check)
- Analyst Recommendation < 2.6 (1=Strong Buy, 5=Sell)
- Avg Volume > 500k (institutionelle Liquiditaet)
- Market Cap > 2500M (keine Micro-Caps)
- Kein Biotech (zu volatil fuer Covered Calls)
- Keine Leveraged/Inverse ETFs (Decay-Risiko)
- IV/HV Ratio Check (faire Praemie vs. Risiko)

**Vorteil ITM Calls:** Hoehere Downside Protection als OTM, weniger Richtungsrisiko.
Nachteil: Geringerer maximaler Gewinn (auf Strike gekappt).
    """)
