import logging
from datetime import datetime

import streamlit as st
import pandas as pd
import sys
import os

from config import PATH_DATABASE_QUERY_FOLDER
from src.historization import select_timetravel_into_dataframe
from src.logger_config import setup_logging
from src.page_display_dataframe import page_display_dataframe
from src.documentation_renderer import render_married_put_analysis_documentation
from src.streamlit_helpers import render_date_filter

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.database import select_into_dataframe

setup_logging(component="streamlit", log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)

# Cached data loading function
@st.cache_data(ttl=300)
def get_married_put_data(selected_date, strike_multiplier):
    """Fetch married put data from database with caching."""
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'married_put.sql'
    return select_timetravel_into_dataframe(
        date=selected_date,
        sql_file_path=sql_file_path,
        params={"strike_multiplier": strike_multiplier}
    )

@st.cache_data(ttl=300)
def get_option_data_at_date(option_osi, selected_date):
    sql = """
        SELECT
            option_osi,
            symbol,
            contract_type,
            expiration_date,
            strike_price,
            premium_option_price,
            intrinsic_value,
            extrinsic_value,
            shares_per_contract,
            live_stock_price,
            open_interest,
            days_to_expiration
        FROM "OptionDataMerged"
        WHERE option_osi = :option_osi
    """
    return select_timetravel_into_dataframe(
        date=selected_date,
        query=sql,
        params={"option_osi": option_osi}
    )

@st.cache_data(ttl=300)
def get_stock_data_at_date(symbol, selected_date):
    sql = """
        SELECT
            symbol,
            close AS close_price,
            adjclose AS adjclose,
            dividends
        FROM "StockPricesYahoo"
        WHERE symbol = :symbol
    """
    return select_timetravel_into_dataframe(
        date=selected_date,
        query=sql,
        params={"symbol": symbol}
    )

@st.cache_data(ttl=300)
def get_dividends_between_dates(symbol, from_date, to_date):
    sql = """
        SELECT COALESCE(SUM(dividends), 0) AS dividend_sum
        FROM "StockPricesYahooHistoryDaily"
        WHERE symbol = :symbol
          AND snapshot_date > :from_date
          AND snapshot_date <= :to_date
    """
    df = select_into_dataframe(query=sql, params={
        "symbol": symbol,
        "from_date": from_date,
        "to_date": to_date,
    })
    if df.empty:
        return 0.0
    return float(df.iloc[0]["dividend_sum"] or 0.0)


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value

# Titel
st.subheader("Married Put Analysis")

selected_date = render_date_filter(
    date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
)

# Filter Controls
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    max_results = st.number_input("Max Results", min_value=10, max_value=1000, value=50, step=10)

with col2:
    min_roi = st.number_input("Min ROI %", min_value=0.0, max_value=100.0, value=3.0, step=1.0)

with col3:
    max_roi = st.number_input("Max ROI %", min_value=0.0, max_value=100.0, value=7.0, step=1.0)

with col4:
    strike_multiplier = st.number_input("Strike > Stock ×", min_value=1.0, max_value=2.0, value=1.2, step=0.05, format="%.2f",
                                         help="Strike muss größer sein als Aktienkurs × dieser Faktor (z.B. 1.0 = ITM, 1.2 = Deep ITM)")

with col5:
    days_range = st.slider("Days to Expiration", min_value=30, max_value=720, value=(30, 500), step=30)

# Row 2 for Status Filter (Checkboxes)
st.write("---")
st.caption("Dividend Growth Status")

def _on_click_alle():
    """Callback – runs BEFORE next rerun, so widget keys can still be set."""
    st.session_state["chk_contender"] = False
    st.session_state["chk_challenger"] = False
    st.session_state["chk_champion"] = False
    st.session_state["chk_show_all"] = True

cb_cols = st.columns([1, 1, 1, 0.8])

with cb_cols[0]:
    chk_contender = st.checkbox("Contender", value=True, key="chk_contender")
with cb_cols[1]:
    chk_challenger = st.checkbox("Challenger", value=True, key="chk_challenger")
with cb_cols[2]:
    chk_champion = st.checkbox("Champion", value=True, key="chk_champion")
with cb_cols[3]:
    st.button("Alle (kein Filter)", key="btn_select_all", on_click=_on_click_alle)

# "Alle" means no classification filter at all
show_all = st.session_state.get("chk_show_all", False)

# If any individual checkbox is toggled, deactivate "show all"
if any([chk_contender, chk_challenger, chk_champion]):
    show_all = False
    st.session_state["chk_show_all"] = False

# Build selected statuses list from checkboxes
selected_statuses = []
if not show_all:
    if chk_contender:
        selected_statuses.append("Dividend Contender")
    if chk_challenger:
        selected_statuses.append("Dividend Challenger")
    if chk_champion:
        selected_statuses.append("Dividend Champion")

# Auto-load data on page load or when filters change
# Using session state to track if data needs to be reloaded
filter_key = f"{selected_date}_{max_results}_{min_roi}_{max_roi}_{strike_multiplier}_{days_range}_{selected_statuses}_{show_all}"
if 'last_filter_key' not in st.session_state or st.session_state['last_filter_key'] != filter_key:
    st.session_state['last_filter_key'] = filter_key
    
    with st.spinner("Loading married put analysis..."):
        try:
            # Execute SQL query with caching
            logger.info(f"Loading married put data for date={selected_date}, strike_multiplier={strike_multiplier}")
            df = get_married_put_data(selected_date=selected_date, strike_multiplier=strike_multiplier)
            logger.info(f"Data loaded. Rows: {len(df) if df is not None else 0}")
            
            if df is not None and not df.empty:
                # Apply ROI filters
                df = df[
                    (df['roi_annualized_pct'] >= min_roi) & 
                    (df['roi_annualized_pct'] <= max_roi)
                ]
                
                # Apply days filter
                df = df[
                    (df['days_to_expiration'] >= days_range[0]) & 
                    (df['days_to_expiration'] <= days_range[1])
                ]

                # Apply Status Filter (skip if "Alle" is active)
                if not show_all and selected_statuses:
                     # 'Classification' is the column name in the DF (aliased from dividend_classification)
                    df = df[df['Classification'].isin(selected_statuses)]
                
                # Limit results
                df = df.head(max_results)
                
                # Store in session state
                st.session_state['married_put_df'] = df
                
            else:
                st.warning("No data found")
                st.session_state['married_put_df'] = pd.DataFrame()
                
        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.session_state['married_put_df'] = pd.DataFrame()

# Display data if it exists
if 'married_put_df' in st.session_state and not st.session_state['married_put_df'].empty:
    df = st.session_state['married_put_df']
    
    # Symbol filter
    symbols = ['All'] + sorted(df['symbol'].unique().tolist())
    selected_symbol = st.selectbox("Filter by Symbol", symbols)
    
    # Apply symbol filter
    display_df = df if selected_symbol == 'All' else df[df['symbol'] == selected_symbol]
    
    # All columns for display (matching SQL query output)
    key_columns = [
        'symbol', 'Company', 'Sector', 'Industry',
        'expiration_date', 'days_to_expiration',
        'strike_price', 'live_stock_price', 'premium_option_price',
        'intrinsic_value', 'extrinsic_value',
        'total_investment', 'minimum_potential_profit',
        'roi_pct', 'roi_annualized_pct',
        'max_loss_total', 'total_return',
        'delta', 'impliedVolatility', 'open_interest',
        'Classification', 'No-Years', 'Current-Div',
        'Payouts/-Year', 'dividends_to_expiration', 'dividend_sum_to_expiration',
        'dividends_to_break_even',
        'earnings_date', 'days_to_earnings',
        'analyst_mean_target_price_year',
        'spread_ptc',
        'strike_stock_price_difference', 'strike_stock_price_difference_ptc',
    ]
    
    # Filter columns that actually exist in the dataframe
    available_columns = [col for col in key_columns if col in display_df.columns]

    # show final dataframe with row selection for documentation
    event = st.dataframe(
        display_df[available_columns],
        width="stretch",
        height=min(800, 40 + 35 * len(display_df)),
        selection_mode="single-row",
        on_select="rerun",
        key="married_put_table",
        column_config={
            "roi_annualized_pct": st.column_config.NumberColumn(
                "ROI % (Annual)",
                format="%.2f%%"
            ),
            "roi_pct": st.column_config.NumberColumn(
                "ROI %",
                format="%.2f%%"
            ),
            "total_investment": st.column_config.NumberColumn(
                "Total Investment",
                format="$%.2f"
            ),
            "minimum_potential_profit": st.column_config.NumberColumn(
                "Min Profit",
                format="$%.2f"
            ),
            "max_loss_total": st.column_config.NumberColumn(
                "Max Loss",
                format="$%.2f"
            ),
            "total_return": st.column_config.NumberColumn(
                "Total Return",
                format="$%.2f"
            ),
            "live_stock_price": st.column_config.NumberColumn(
                "Stock Price",
                format="$%.2f"
            ),
            "strike_price": st.column_config.NumberColumn(
                "Strike",
                format="$%.2f"
            ),
            "premium_option_price": st.column_config.NumberColumn(
                "Option Premium",
                format="$%.2f"
            ),
            "intrinsic_value": st.column_config.NumberColumn(
                "Intrinsic Value",
                format="$%.2f"
            ),
            "extrinsic_value": st.column_config.NumberColumn(
                "Extrinsic Value",
                format="$%.2f"
            ),
            "impliedVolatility": st.column_config.NumberColumn(
                "IV",
                format="%.2f"
            ),
            "spread_ptc": st.column_config.NumberColumn(
                "Spread %",
                format="%.2f%%"
            ),
            "strike_stock_price_difference": st.column_config.NumberColumn(
                "Strike-Stock Diff",
                format="$%.2f"
            ),
            "strike_stock_price_difference_ptc": st.column_config.NumberColumn(
                "Strike-Stock Diff %",
                format="%.2f%%"
            ),
            "dividend_sum_to_expiration": st.column_config.NumberColumn(
                "Div Sum to Exp",
                format="$%.2f"
            ),
            "analyst_mean_target_price_year": st.column_config.NumberColumn(
                "Analyst Target",
                format="$%.2f"
            ),
            "Classification": st.column_config.TextColumn(
                "Dividend Status"
            ),
        }
    )

    # ── Inline Documentation on row click ──────────────────────────
    @st.fragment
    def show_documentation():
        selected_rows = event.selection.rows if hasattr(event, "selection") else []
        if selected_rows and not display_df.empty:
            selected_idx = selected_rows[0]
            selected_row = display_df.iloc[selected_idx]

            # Simulate hold and exit performance if the user chooses a comparison date
            st.divider()
            st.subheader("📈 Simulierter Exit zum Vergleichsdatum")
            compare_date = render_date_filter(
                date_query='select date from (select date from "DatesHistory" union select current_date) as sub ORDER BY date DESC',
                date_label="Vergleichsdatum für Verkauf:",
                date_session_key="selected_compare_date",
                date_list_session_key="date_list_compare",
                date_index=0,
            )

            if compare_date == selected_date:
                st.info("Wähle ein anderes Datum als das Einstiegdatum, um die Haltedauer zu simulieren.")
            else:
                selected_row = selected_row.copy()
                initial_stock_price = float(selected_row["live_stock_price"])
                initial_option_price = float(selected_row["premium_option_price"])
                number_of_stocks = int(selected_row["number_of_stocks"])
                option_osi = selected_row.get("option_osi")
                strike_price = float(selected_row["strike_price"])
                expiration_date = parse_date(selected_row["expiration_date"])

                option_exit_df = None
                if option_osi:
                    option_exit_df = get_option_data_at_date(option_osi, compare_date)

                stock_exit_df = get_stock_data_at_date(selected_row["symbol"], compare_date)
                dividends_paid_total = get_dividends_between_dates(
                    selected_row["symbol"],
                    selected_date,
                    compare_date,
                ) * number_of_stocks

                if stock_exit_df is None or stock_exit_df.empty:
                    st.warning("Kein Kursverlauf für das Vergleichsdatum verfügbar.")
                else:
                    stock_exit_price = float(stock_exit_df.iloc[0]["close_price"])
                    if option_exit_df is not None and not option_exit_df.empty:
                        option_exit_price = float(option_exit_df.iloc[0]["premium_option_price"])
                    else:
                        option_exit_price = None

                    if parse_date(compare_date) <= expiration_date and option_exit_price is not None:
                        option_value_end = option_exit_price * number_of_stocks
                        option_exit_label = f"Option-Prämie bei Exit"
                        option_exit_value = f"${option_exit_price:.2f}"
                    else:
                        option_intrinsic = max(0.0, strike_price - stock_exit_price)
                        option_value_end = option_intrinsic * number_of_stocks
                        option_exit_label = (
                            f"Option-Intrinsischer Wert bei Exit"
                            + (" (nach Ablauf)" if parse_date(compare_date) > expiration_date else "")
                        )
                        option_exit_value = f" ${option_intrinsic:.2f}"

                    investment_start = number_of_stocks * (initial_stock_price + initial_option_price) + 3.5
                    closing_stock_value = stock_exit_price * number_of_stocks
                    total_end_value = closing_stock_value + option_value_end + dividends_paid_total
                    profit = total_end_value - investment_start
                    days_held = (parse_date(compare_date) - parse_date(selected_date)).days
                    roi_pct = profit / investment_start * 100 if investment_start else 0.0
                    roi_annualized_pct = (
                        profit / investment_start * 365.0 / days_held * 100
                        if investment_start and days_held > 0
                        else None
                    )

                    comparison_cols = st.columns(3)
                    with comparison_cols[0]:
                        st.metric("Einstiegsdatum", str(selected_date))
                        st.metric("Einstiegspreis Aktie", f"${initial_stock_price:.2f}")
                        st.metric("Einstiegspreis Put", f"${initial_option_price:.2f}")
                        st.metric("Investition gesamt", f"${investment_start:.2f}")

                    with comparison_cols[1]:
                        st.metric("Vergleichsdatum", str(compare_date))
                        st.metric("Schlusskurs Aktie", f"${stock_exit_price:.2f}")
                        st.metric(option_exit_label, option_exit_value)
                        st.metric("Endwert Position", f"${total_end_value:.2f}")
                        st.metric("Dividenden erhalten", f"${dividends_paid_total:.2f}")
                        

                    with comparison_cols[2]:
                        st.metric("Tage gehalten", f"{days_held}")
                        stock_change_pct = (stock_exit_price / initial_stock_price - 1) * 100 if initial_stock_price else 0.0
                        st.metric(f"Aktie-Preisänderung", f"{stock_change_pct:+.2f}%")
                        if option_exit_price is not None and parse_date(compare_date) <= expiration_date:
                            option_change_pct = (option_exit_price / initial_option_price - 1) * 100 if initial_option_price else 0.0
                            st.metric(f"Option-Preisänderung", f"{option_change_pct:+.2f}%")
                        elif parse_date(compare_date) > expiration_date:
                            st.write("Der Vergleichszeitpunkt liegt nach dem Verfallsdatum; der Wert wird über den intrinsischen Wert berechnet.")
                        st.metric("Gewinn/Verlust", f"${profit:.2f}")
                        st.metric("ROI", f"{roi_pct:.2f}%")
                        if roi_annualized_pct is not None:
                            st.metric("Annualisierter ROI", f"{roi_annualized_pct:.2f}%")
                        else:
                            st.write("Annualisierter ROI: n/a")

            st.divider()
            doc_md = render_married_put_analysis_documentation(row=selected_row)
            st.markdown(doc_md)
                    
        else:
            st.caption("💡 Klicke auf eine Zeile in der Tabelle, um die vollständige Berechnung für diese Option zu sehen.")
    
    show_documentation()

else:
    st.info("No data available")
    
# Info box with strategy explanation
with st.expander("Strategy Information"):
    st.markdown("""
    **Married Put Strategy:**
    - Delta > abs(-0.85): Probability of finishing in the money
    - A put with Delta -0.30 means ~30% chance it will expire in the money
    - Payout ratio < 100% (earnings should cover dividend)  
    - Buy at small implied volatility < 30%
    - Exercise and unbook stocks only at the end
    - If the option still has time value, it makes sense to sell the put separately
    
    **Filters Applied:**
    - Only PUT options
    - Strike > Stock Price * 1.2 (OTM puts)
    - Extrinsic value > 0
    - Option open interest > 0
    - Days to expiration > User Selection (Range)
    - Dividend Status matching selection
    - Top 3 options per symbol by ROI
    """)