import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

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
from src.database import select_into_dataframe

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

@st.cache_data(ttl=300)
def get_married_put_stock_range(symbol, from_date, to_date):
    """Holt die tagesgenauen historischen Aktienkurse für den Chart"""
    sql = """
        SELECT date, symbol, close
        FROM "StockPricesYahooHistory"
        WHERE symbol = :symbol
        AND date BETWEEN :from_date AND :to_date
    """
    return select_into_dataframe(query=sql, params={"symbol": symbol, "from_date": from_date, "to_date": to_date})

@st.cache_data(ttl=300)
def get_married_put_option_range(option_osi, from_date, to_date):
    """Holt die tagesgenauen historischen Optionspreise für den Chart"""
    sql = """
        SELECT date, option_osi, day_close AS premium_option_price
        FROM "OptionDataMassiveHistory"
        WHERE option_osi = :option_osi
        AND date BETWEEN :from_date AND :to_date
    """
    return select_into_dataframe(query=sql, params={"option_osi": option_osi, "from_date": from_date, "to_date": to_date})

def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    return value

def display_married_put_backtesting(selected_date, selected_row):  
    # Simulate hold and exit performance if the user chooses a comparison date
            

    st.divider()
    st.subheader("📈 Simulierter Exit zum Vergleichsdatum")
    compare_date = render_date_filter(
        date_query=f'select date from (select date from "DatesHistory" union select current_date) as sub WHERE date > \'{selected_date}\' AND date <= \'{selected_row["expiration_date"]}\' ORDER BY date DESC',
        date_label="Vergleichsdatum für Verkauf:",
        date_session_key="selected_compare_date",
        date_list_session_key="date_list_compare",
        date_index=0,
    )

    if not compare_date:
        return

    selected_row = selected_row.copy()
    initial_stock_price = float(selected_row["live_stock_price"])
    initial_option_price = float(selected_row["premium_option_price"])
    number_of_stocks = int(selected_row["number_of_stocks"])
    option_osi = selected_row.get("option_osi")
    strike_price = float(selected_row["strike_price"])
    expiration_date = parse_date(selected_row["expiration_date"])

    option_exit_df = None
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        option_exit_future = executor.submit(get_option_data_at_date, option_osi, compare_date)
        stock_exit_future = executor.submit(get_stock_data_at_date, selected_row["symbol"], compare_date)
        dividends_future = executor.submit(get_dividends_between_dates, selected_row["symbol"], selected_date, compare_date)
        stock_range_future = executor.submit(get_married_put_stock_range, selected_row["symbol"], selected_date, compare_date)
        option_range_future = executor.submit(get_married_put_option_range, option_osi, selected_date, compare_date)
        
        option_exit_df = option_exit_future.result()
        stock_exit_df = stock_exit_future.result()
        dividends_paid_total = dividends_future.result() * number_of_stocks
        
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

            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            st.markdown("---")
            st.markdown("### 📈 Tagesgenauer Performance- & Absicherungsverlauf")

            # Historische Datenbereiche abfragen
            hist_stock_df = stock_range_future.result()
            hist_option_df = option_range_future.result()

        if hist_stock_df is None or hist_option_df is None or hist_stock_df.empty or hist_option_df.empty:
            st.info("💡 Keine ausreichenden historischen Tagesdaten für eine detaillierte Verlaufskurve gefunden.")
        else:
            # Datentypen für den Merge angleichen (Strings)
            hist_stock_df['date'] = hist_stock_df['date'].astype(str)
            hist_option_df['date'] = hist_option_df['date'].astype(str)

            # Tabellen über das Datum zusammenführen
            merged_hist = hist_stock_df[['date', 'close']].merge(
                hist_option_df[['date', 'premium_option_price']], on='date', how='inner'
            ).sort_values('date')

            if merged_hist.empty:
                st.warning("Keine Schnittmenge an historischen Daten für diesen Zeitraum gefunden.")
            else:
                # Mathematische Linien berechnen
                breakeven_line = initial_stock_price + initial_option_price
                
                # Gesamtwert der kombinierten Position pro Aktie (Aktie + Put-Preis)
                merged_hist['combined_value'] = merged_hist['close'] + merged_hist['premium_option_price']
                
                # Gesamtkosten für 100 Aktien + 1 Kontrakt beim Einstieg
                initial_total_cost = breakeven_line * 100
                
                # Tagesgenaue GuV-Entwicklung für das gesamte Paket
                merged_hist['daily_p_l_total'] = (merged_hist['combined_value'] * 100) - initial_total_cost

                # Subplot mit dualer Y-Achse initialisieren
                fig = make_subplots(specs=[[{"secondary_y": True}]])

                # 1. TRACE: Der reine Aktienkurs (Linke Achse - Gepunktet)
                fig.add_trace(
                    go.Scatter(
                        x=merged_hist['date'], y=merged_hist['close'],
                        mode='lines', name='Reiner Aktienkurs (links)',
                        line=dict(color='#1f77b4', width=2, dash='dot')
                    ), secondary_y=False
                )

                # 2. TRACE: Der Gesamtwert des "Married Put"-Pakets (Linke Achse - Solide)
                fig.add_trace(
                    go.Scatter(
                        x=merged_hist['date'], y=merged_hist['combined_value'],
                        mode='lines', name='Kombinierter Wert (Aktie + Put) (links)',
                        line=dict(color='#2ca02c', width=3)
                    ), secondary_y=False
                )

                # 3. TRACE: Echter Gewinn/Verlust in USD auf deinem Konto (Rechte Achse)
                fig.add_trace(
                    go.Scatter(
                        x=merged_hist['date'], y=merged_hist['daily_p_l_total'],
                        mode='lines+markers', name='Realer GuV Kontostand $ (rechts)',
                        line=dict(color='#9467bd', width=2.5),
                        marker=dict(size=4)
                    ), secondary_y=True
                )

                # HORIZONTALE REFERENZLINIEN (Bezogen auf die linke Preis-Achse)
                # Breakeven Level (Gewinnschwelle)
                fig.add_hline(y=breakeven_line, line_dash="dash", line_color="orange",
                                annotation_text=f"Breakeven (${breakeven_line:.2f})", annotation_position="top left")

                # Absicherungs-Strike (Ab hier verliert die Position kein Geld mehr, egal wie tief die Aktie fällt)
                fig.add_hline(y=strike_price, line_dash="dash", line_color="red",
                                annotation_text=f"Put Strike Schutz (${strike_price:.2f})", annotation_position="bottom left")

                # Layout- & Farb-Styling für Streamlit
                fig.update_layout(
                    title=f"Historischer Verlauf für {selected_row["symbol"]} (Gesamteinstiegskosten: ${initial_total_cost:.2f})",
                    xaxis_title="Handelstag",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.1)"),
                    margin=dict(l=20, r=20, t=50, b=20)
                )

                fig.update_yaxes(title_text="Wert / Preis pro Aktie ($)", gridcolor='rgba(128,128,128,0.15)', secondary_y=False)
                fig.update_yaxes(title_text="Echter GuV-Kontostand ($)", gridcolor='rgba(148,103,189,0.1)', secondary_y=True)

                # Statische Nulllinie für das rechte GuV-Guthaben (Wechsel zwischen Gewinn- und Verlustzone)
                fig.add_shape(
                    type="line", x0=merged_hist['date'].iloc[0], x1=merged_hist['date'].iloc[-1],
                    y0=0, y1=0, line=dict(color="rgba(128,128,128,0.5)", width=1.5),
                    yref="y2" # Wichtig: Bindung an die rechte Achse!
                )

                st.plotly_chart(fig, use_container_width=True)

                # Zusätzliche Textbox zur Erklärung der Strategiezonen am ausgewählten Trade
                max_loss_total = (breakeven_line - strike_price) * 100
                st.info(
                    f"🛡️ **Strategie-Analyse:** Dein maximales Risiko bei diesem Trade war von Tag 1 an auf "
                    f"**${max_loss_total:.2f}** limitiert. Selbst wenn die Aktie auf $0 gefallen wäre, hättest du "
                    f"wegen des Puts bei ${strike_price:.2f} nicht mehr verlieren können. "
                    f"Die lila Linie zeigt dir, ab wann du die Gewinnzone (über der grauen Nulllinie) erreicht hast."
                )