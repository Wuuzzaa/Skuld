import logging
import os
from concurrent.futures import ThreadPoolExecutor
from src.data_aging import is_weekend
from src.database import select_into_dataframe
from src.historization import select_timetravel_into_dataframe
from src.streamlit_helpers import render_date_filter
import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
import plotly.graph_objects as go

logger = logging.getLogger(os.path.basename(__file__))

def parse_date(value):
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


@st.cache_data(ttl=300)
def get_option_data_at_date(option_osi, symbol, selected_date):
    if str(selected_date) == str(time.strftime("%Y-%m-%d", time.gmtime())) and not is_weekend():
        sql = f"""
            SELECT
                a.option_osi,
                a.symbol,
                a.contract_type,
                a.expiration_date,
                a.strike_price,
                a.day_close AS premium_option_price,
                a.shares_per_contract,
                b.close
            FROM "OptionDataMassiveHistory" AS a
            INNER JOIN "StockPricesYahooHistory" AS b
            ON a.date = b.date AND a.symbol = b.symbol
            WHERE a.option_osi = :option_osi
            AND a.symbol = :symbol
            AND b.symbol = :symbol
            AND a.date BETWEEN '{selected_date}'::date - INTERVAL '1 week' AND '{selected_date}'::date
            AND b.date BETWEEN '{selected_date}'::date - INTERVAL '1 week' AND '{selected_date}'::date
            ORDER BY a.date DESC
            LIMIT 1
        """
    else:
        sql = f"""
            SELECT
                a.option_osi,
                a.symbol,
                a.contract_type,
                a.expiration_date,
                a.strike_price,
                a.day_close AS premium_option_price,
                a.shares_per_contract,
                b.close
            FROM (
                SELECT * FROM "OptionDataMassiveHistory"
                UNION ALL
                SELECT CURRENT_DATE AS date, * FROM "OptionDataMassive"
            ) AS a
            INNER JOIN "StockPricesYahooHistory" AS b
            ON a.date = b.date AND a.symbol = b.symbol
            WHERE a.option_osi = :option_osi
            AND a.symbol = :symbol
            AND b.symbol = :symbol
            AND a.date BETWEEN '{selected_date}'::date - INTERVAL '1 week' AND '{selected_date}'::date
            AND b.date BETWEEN '{selected_date}'::date - INTERVAL '1 week' AND '{selected_date}'::date
            ORDER BY a.date DESC
            LIMIT 1
        """
    return select_into_dataframe(
        query=sql,
        params={"option_osi": option_osi, "symbol": symbol}
    )

@st.cache_data(ttl=300)
def get_option_date_range(option_osi, from_date, to_date):
    if str(to_date) == str(time.strftime("%Y-%m-%d", time.gmtime())) and not is_weekend():
      sql = """
            SELECT
                date,
                option_osi,
                symbol,
                contract_type,
                expiration_date,
                strike_price,
                day_close AS premium_option_price,
                shares_per_contract
            FROM "OptionDataMassiveHistory"
            WHERE option_osi = :option_osi
            AND date BETWEEN :from_date AND :to_date
            AND date <> CURRENT_DATE
            UNION ALL
            SELECT
                CURRENT_DATE AS date,
                option_osi,
                symbol,
                contract_type,
                expiration_date,
                strike_price,
                day_close AS premium_option_price,
                shares_per_contract
            FROM "OptionDataMassive"
            WHERE option_osi = :option_osi
        """ 
    else:
        sql = """
            SELECT
                date,
                option_osi,
                symbol,
                contract_type,
                expiration_date,
                strike_price,
                day_close AS premium_option_price,
                shares_per_contract
            FROM "OptionDataMassiveHistory"
            WHERE option_osi = :option_osi
            AND date BETWEEN :from_date AND :to_date
        """
    return select_into_dataframe(
        query=sql,
        params={"option_osi": option_osi, "from_date": from_date, "to_date": to_date}
    )

@st.cache_data(ttl=300)
def get_stock_date_range(symbol, from_date, to_date):
    if str(to_date) == str(time.strftime("%Y-%m-%d", time.gmtime())) and not is_weekend():
        sql = """
            SELECT
                date,
                symbol,
                close
            FROM "StockPricesYahooHistory"
            WHERE symbol = :symbol
            AND date BETWEEN :from_date AND :to_date
            AND date <> CURRENT_DATE
            UNION ALL
            SELECT
                CURRENT_DATE AS date,
                symbol,
                close
            FROM "StockPricesYahoo"
            WHERE symbol = :symbol
        """
    else:
        sql = """
            SELECT
                date,
                symbol,
                close
            FROM "StockPricesYahooHistory"
            WHERE symbol = :symbol
            AND date BETWEEN :from_date AND :to_date
        """
    return select_into_dataframe(
        query=sql,
        params={"symbol": symbol, "from_date": from_date, "to_date": to_date}
    )

def display_spreads_backtesting(selected_date, selected_row):
     # Time Travel Simulation for the selected comparison date
    st.divider()
    st.subheader("📈 Simulierter Exit zum Vergleichsdatum")
    compare_date = render_date_filter(
        date_query=f'select date from (select date from "DatesHistory" union select current_date) as sub  WHERE date > \'{selected_date}\' AND date <= \'{selected_row["expiration_date"]}\' ORDER BY date DESC',
        date_label="Vergleichsdatum für Verkauf:",
        date_session_key="spread_compare_date",
        date_list_session_key="spread_date_list_compare" + str(selected_row['expiration_date'].strftime('%Y%m%d')),
        date_index=0,
    )

    if not compare_date:
        return


    if parse_date(compare_date) == parse_date(selected_date):
        st.info("Wähle ein anderes Vergleichsdatum als das Einstiegdatum.")
    else:
        with ThreadPoolExecutor(max_workers=5) as executor:
            sell_exit_future = executor.submit(get_option_data_at_date, selected_row['sell_option_osi'], selected_row['symbol'], compare_date)
            buy_exit_future = executor.submit(get_option_data_at_date, selected_row['buy_option_osi'], selected_row['symbol'], compare_date)
            sell_option_date_range_future = executor.submit(get_option_date_range, selected_row['sell_option_osi'], selected_date, compare_date)
            buy_option_date_range_future = executor.submit(get_option_date_range, selected_row['buy_option_osi'], selected_date, compare_date)
            stock_date_range_future = executor.submit(get_stock_date_range, selected_row['symbol'], selected_date, compare_date)
            
            sell_exit_df = sell_exit_future.result()
            buy_exit_df = buy_exit_future.result()

            logger.info(f"Sell Option data Points {len(sell_exit_df)}")
            logger.info(f"Buy Option data Points {len(buy_exit_df)}")

            if sell_exit_df is None or buy_exit_df is None or sell_exit_df.empty or buy_exit_df.empty:
                st.warning("Die Option konnte für das Vergleichsdatum nicht geladen werden.")
            else:
                # [DEIN BESTEHENDER CODE: 1. Daten auslesen und 2. Mathematische Berechnungen bleiben exakt gleich]
                exit_sell_price = float(sell_exit_df.iloc[0]['premium_option_price'])
                exit_buy_price = float(buy_exit_df.iloc[0]['premium_option_price'])   
                exit_stock_price = float(buy_exit_df.iloc[0]['close'])        

                entry_sell_price = float(selected_row['sell_last_option_price'])
                entry_buy_price = float(selected_row['buy_last_option_price'])
                entry_stock_price = float(selected_row['close'])

                # --- NEU: Optionale manuelle Preiskorrektur ---
                st.markdown("### 🛠️ Echte Ausführungskurse (Optional)")
                override_prices = st.checkbox(
                    "Tatsächliche Ausführungspreise (Fills) manuell eintragen", 
                    value=False,
                    help="Aktiviere dies, um die historischen Kurse durch deine realen Kauf-/Verkaufspreise zu ersetzen."
                )

                # Variable für Gebühren standardmäßig auf 0.0 setzen
                start_transaction_cost = 0.0
                exit_transaction_cost = 0.0

                if override_prices:
                    # Platzsparende Spalten für Einstieg und Ausstieg
                    edit_cols = st.columns(2)
                    
                    with edit_cols[0]:
                        st.caption("🛫 Realer Einstieg (Credit)")
                        entry_sell_price = st.number_input(
                            "Short Put Verkaufspreis ($)", 
                            min_value=0.0, value=entry_sell_price, step=0.01, format="%.2f"
                        )
                        entry_buy_price = st.number_input(
                            "Long Put Kaufpreis ($)", 
                            min_value=0.0, value=entry_buy_price, step=0.01, format="%.2f"
                        )
                        start_transaction_cost = st.number_input(
                            "Kauf Ordergebühren ($)", 
                            min_value=0.0, value=0.0, step=0.50, format="%.2f",
                            help="Trage hier die gesamten Gebühren (Einstieg für alle Kontrakte) ein."
                        )
                        
                    with edit_cols[1]:
                        st.caption("🛬 Realer Ausstieg (Debit)")
                        exit_sell_price = st.number_input(
                            "Short Put Rückkaufpreis ($)", 
                            min_value=0.0, value=exit_sell_price, step=0.01, format="%.2f"
                        )
                        exit_buy_price = st.number_input(
                            "Long Put Verkaufspreis ($)", 
                            min_value=0.0, value=exit_buy_price, step=0.01, format="%.2f"
                        )
                        exit_transaction_cost = st.number_input(
                            "Verkauf Ordergebühren ($)", 
                            min_value=0.0, value=0.0, step=0.50, format="%.2f",
                            help="Trage hier die gesamten Gebühren (Ausstieg für alle Kontrakte) ein."
                        )
            
                    st.markdown("---")
                # --- Ende der Neuerung ---

                strike_sell = float(selected_row['sell_strike'])
                strike_buy = float(selected_row['buy_strike'])
                spread_width = abs(strike_sell - strike_buy)

                initial_cash_flow = (entry_sell_price - entry_buy_price) * 100 - start_transaction_cost
                close_cash_flow = (exit_buy_price - exit_sell_price) * 100 - exit_transaction_cost
                profit = initial_cash_flow + close_cash_flow

                if parse_date(compare_date) >= parse_date(selected_row['expiration_date']):
                    close_cash_flow = 0
                    exit_buy_price = 0
                    exit_sell_price = 0

                if initial_cash_flow > 0:
                    bpr_capital = spread_width * 100 - initial_cash_flow
                else:
                    bpr_capital = abs(initial_cash_flow)

                bpr_capital_total = bpr_capital
                profit_total = profit
                roi_pct = (profit / bpr_capital * 100) if bpr_capital > 0 else None
                max_profit_pct = profit / initial_cash_flow * 100
                # roi_pct = (profit / initial_cash_flow * 100) if initial_cash_flow > 0 else None

                # [DEIN BESTEHENDER CODE: 3. Visuelle Darstellung (KPIs und Spalten) bleibt unverändert]
                st.markdown("### 📊 Trade-Analyse & Performance")
                # Oberste Reihe: Die wichtigsten harten Fakten als Key Performance Indicators (KPIs)
                kpi_cols = st.columns(6)
                with kpi_cols[0]:
                    st.metric("Max Profit", f"${(initial_cash_flow):+.2f}")
                with kpi_cols[1]:
                    st.metric("Aktueller Profit", f"${profit_total:+.2f}", delta=f"{profit_total:+.2f}$")
                with kpi_cols[2]:
                    if max_profit_pct is not None:
                        st.metric("Unrealized Profit", f"{max_profit_pct:.2f}%", delta=f"{max_profit_pct:.2f}%")
                    else:
                        st.metric("Profit", "n/a")
                with kpi_cols[3]:
                    if roi_pct is not None:
                        st.metric("Echter ROI (on Risk)", f"{roi_pct:.2f}%", delta=f"{roi_pct:.2f}%")
                    else:
                        st.metric("Echter ROI", "n/a")
                with kpi_cols[4]:
                    st.metric("Riskiertes Kapital (BPR)", f"${bpr_capital_total:.2f}", help="Das gebundene Kapital auf dem Konto")
                with kpi_cols[5]:
                    st.metric("Spread-Breite", f"${spread_width:.2f}")

                st.markdown("---")

                # Zweite Reihe: Verlauf des Trades (Einstieg vs. Ausstieg)
                comparison_cols = st.columns(3)

                with comparison_cols[0]:
                    st.subheader("🛫 1. Einstieg")
                    st.caption(f"Datum: {selected_date}")
                    st.metric("Initiale Prämie", f"{initial_cash_flow:+.2f} $", help="Positiv = Einnahme (Credit)")
                    st.text(f"Short Option: ${entry_sell_price:.2f}")
                    st.text(f"Long Option:  ${entry_buy_price:.2f}")

                with comparison_cols[1]:
                    st.subheader("🛬 2. Ausstieg")
                    st.caption(f"Datum: {compare_date}")
                    # Zeigt an, wie viel der Spread beim Schließen wert war (z.B. 0.01 $)
                    st.metric("Restwert Spread", f"${close_cash_flow:.2f}", help="Idealerweise nahe 0$ bei Credit Spreads")
                    st.text(f"Short-Rückkauf: ${exit_sell_price:.2f}")
                    st.text(f"Long-Verkauf:  ${exit_buy_price:.2f}")

                with comparison_cols[2]:
                    st.subheader("💡 Trade Status")
                    days_held = (parse_date(compare_date) - parse_date(selected_date)).days
                    st.caption(f"Tage gehalten: {days_held}")
                    roi_annualized_pct = (
                        roi_pct * 365.0 / days_held
                        if roi_pct is not None and days_held > 0
                        else None
                    )
                    if profit > 0:
                        st.success(f"Gewinn-Trade!\nDu hast {roi_pct:.1f}% Rendite auf dein eingesetztes Kapital erzielt.")
                    elif profit < 0:
                        st.error(f"Verlust-Trade.\nVerlust: ${abs(profit_total):.2f}")
                    else:
                        st.info("Break-Even (±0 $)")
                    if roi_annualized_pct is not None:
                        st.metric("Annualisierter ROI", f"{roi_annualized_pct:.2f}%")
                    else:
                        st.write("Annualisierter ROI: n/a")

                # Breakeven berechnen
                breakeven_price = strike_sell - initial_cash_flow

                st.markdown("---")
                st.markdown("### 📈 Kursverlauf & Positions-Wertentwicklung")

                # --- NEU: HISTORISCHE DATEN ZUSAMMENFÜHREN & BERECHNEN ---
                # Sicherstellen, dass das Datum überall denselben Datentyp (String oder Date) hat
                sell_option_date_range_df = sell_option_date_range_future.result()
                buy_option_date_range_df = buy_option_date_range_future.result()
                stock_date_range_df = stock_date_range_future.result()
                logger.info(f"Option data points {len(sell_option_date_range_df)}")
                logger.info(f"Stock data points {len(stock_date_range_df)}")



                stock_df = stock_date_range_df.copy()
                sell_opt_df = sell_option_date_range_df.copy()
                buy_opt_df = buy_option_date_range_df.copy()

                stock_df['date'] = stock_df['date'].astype(str)
                sell_opt_df['date'] = sell_opt_df['date'].astype(str)
                buy_opt_df['date'] = buy_opt_df['date'].astype(str)

                # Umbenennen der Spalten vor dem Zusammenführen, um Namenskonflikte zu vermeiden
                stock_df = stock_df.rename(columns={'close': 'stock_close'})
                sell_opt_df = sell_opt_df.rename(columns={'premium_option_price': 'price_sell_opt'})
                buy_opt_df = buy_opt_df.rename(columns={'premium_option_price': 'price_buy_opt'})

                # Schrittweiser Merge über das Datum
                merged_history = stock_df[['date', 'stock_close']].merge(
                    sell_opt_df[['date', 'price_sell_opt']], on='date', how='inner'
                ).merge(
                    buy_opt_df[['date', 'price_buy_opt']], on='date', how='inner'
                )

                # Sortieren, damit die Zeitlinie stimmt
                merged_history = merged_history.sort_values('date')

                if merged_history.empty:
                    st.warning("Keine übereinstimmenden historischen Tagesdaten für den Chart-Verlauf gefunden.")
                else:
                    # TAGESGENAUE BERECHNUNG DES SPREAD-WERTES (Geldfluss-Sicht / "Buchwert")
                    # Formel: Initialer Credit (+) - (Aktueller Rückkaufpreis des Short Puts (-) + Aktueller Verkaufswert des Long Puts (+))
                    # Rechnerisch: initial_cash_flow + (price_buy_opt - price_sell_opt)
                    # Für die Gesamtdepot-Sicht multiplizieren wir direkt mit 100
                    merged_history['position_value_total'] = (
                        initial_cash_flow + (merged_history['price_buy_opt'] - merged_history['price_sell_opt'])
                    ) * 100

                    # --- PLOTLY CHART MIT ZWEI Y-ACHSEN (MAKE_SUBPLOTS) ---
                    from plotly.subplots import make_subplots

                    # Erstelle Subplot-Gerüst mit dualer Y-Achse
                    fig = make_subplots(specs=[[{"secondary_y": True}]])

                    # 1. TRACE: Aktienkurs (Tagesgenau auf Primär-Achse links)
                    fig.add_trace(
                        go.Scatter(
                            x=merged_history['date'], 
                            y=merged_history['stock_close'], 
                            mode='lines', 
                            name='Aktienkurs (links)',
                            line=dict(color='#1f77b4', width=3) # Klassisches Blau
                        ),
                        secondary_y=False,
                    )

                    # 2. TRACE: Positions-Wertentwicklung (Tagesgenau auf Sekundär-Achse rechts)
                    fig.add_trace(
                        go.Scatter(
                            x=merged_history['date'], 
                            y=merged_history['position_value_total'], 
                            mode='lines+markers', 
                            name='Positions-Wert in $ (rechts)',
                            line=dict(color='#9467bd', width=2.5, dash='solid'), # Lila Linie
                            marker=dict(size=5)
                        ),
                        secondary_y=True,
                    )

                    # HORIZONTALE ZONEN-LINIEN (Beziehen sich auf den Aktienkurs -> secondary_y=False)
                    # Short Strike Put
                    fig.add_hline(y=strike_sell, line_dash="dash", line_color="green", 
                                    annotation_text=f"Short Strike (${strike_sell:.2f})", 
                                    annotation_position="top left")

                    # Breakeven
                    fig.add_hline(y=breakeven_price, line_dash="dot", line_color="orange", 
                                    annotation_text=f"Breakeven (${breakeven_price:.2f})", 
                                    annotation_position="bottom left")

                    # Long Strike Put
                    fig.add_hline(y=strike_buy, line_dash="dash", line_color="red", 
                                    annotation_text=f"Long Strike (${strike_buy:.2f})", 
                                    annotation_position="bottom left")

                    # --- BERECHNUNG DER SYNCHRONISIERTEN ACHSEN-RANGES ---
                    # Wir ermitteln die maximalen Ausschläge der echten Daten von den jeweiligen Nullpunkten (Breakeven bzw. 0)
                    stock_min = merged_history['stock_close'].min()
                    stock_max = merged_history['stock_close'].max()
                    p_l_min = merged_history['position_value_total'].min()
                    p_l_max = merged_history['position_value_total'].max()

                    # Wie weit weichen die Werte maximal nach oben/unten vom jeweiligen Ziel ab?
                    # Für die Aktie ist das Zentrum der Breakeven-Preis
                    stock_max_delta = max(abs(stock_max - breakeven_price), abs(stock_min - breakeven_price), 1.0)
                    # Für die GuV ist das Zentrum exakt 0
                    p_l_max_delta = max(abs(p_l_max - 0), abs(p_l_min - 0), 10.0)

                    # Großzügiges Padding (z.B. 15% Puffer), damit die Linien nicht am Chartrand kleben
                    padding_factor = 1.15
                    stock_range = [breakeven_price - (stock_max_delta * padding_factor), breakeven_price + (stock_max_delta * padding_factor)]
                    p_l_range = [0 - (p_l_max_delta * padding_factor), 0 + (p_l_max_delta * padding_factor)]

                    # LAYOUT & ACHSEN-STYLING (Synchronisiert)
                    fig.update_layout(
                        title="Tagesgenauer Verlauf: Aktienkurs vs. G&V Wertentwicklung",
                        xaxis_title="Datum",
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.2)"),
                        margin=dict(l=20, r=20, t=50, b=20)
                    )

                    # Primäre Achse links (Aktienkurs): Zentriert um den Breakeven-Preis
                    fig.update_yaxes(
                        title_text="Aktienkurs in $", 
                        gridcolor='rgba(128,128,128,0.15)', 
                        secondary_y=False,
                        range=stock_range
                    )

                    # Sekundäre Achse rechts (Positions-Wert): Zentriert um exakt 0
                    fig.update_yaxes(
                        title_text="Positions-Wert (GuV) in $", 
                        gridcolor='rgba(148,103,189,0.1)', 
                        secondary_y=True,
                        range=p_l_range
                    )

                    # Horizontale Nulllinie für den Positions-Wert (Rechte Achse)
                    # Da die Achsen jetzt perfekt zentriert sind, rastet diese Linie exakt auf der orangefarbenen Breakeven-Linie ein!
                    fig.add_shape(
                        type="line", x0=merged_history['date'].iloc[0], x1=merged_history['date'].iloc[-1],
                        y0=0, y1=0, line=dict(color="rgba(148,103,189,0.6)", width=1.5, dash="solid"),
                        yref="y2"
                    )

                    # Chart anzeigen
                    st.plotly_chart(fig, use_container_width=True)

                    # # LAYOUT & ACHSEN-STYLING
                    # fig.update_layout(
                    #     title="Tagesgenauer Verlauf: Aktienkurs vs. G&V Wertentwicklung",
                    #     xaxis_title="Datum",
                    #     paper_bgcolor="rgba(0,0,0,0)",
                    #     plot_bgcolor="rgba(0,0,0,0)",
                    #     legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.2)"),
                    #     margin=dict(l=20, r=20, t=50, b=20)
                    # )

                    # # Achsen-Titel vergeben
                    # fig.update_yaxes(title_text="Aktienkurs in $", gridcolor='rgba(128,128,128,0.15)', secondary_y=False)
                    # fig.update_yaxes(title_text="Positions-Wert (GuV) in $", gridcolor='rgba(148,103,189,0.1)', secondary_y=True,
                    #                 # HIERMIT ERZWINGST DU DIE SYNCHRONISATION DER NULLPUNKTE/ZENTRIERUNGEN
                    #                 scaleanchor="y", 
                    #                 scaleratio=1)

                    # # Horizontale Nulllinie für den Positions-Wert (Rechte Achse), damit man sofort sieht, wann man im Minus war
                    # fig.add_shape(
                    #     type="line", x0=merged_history['date'].iloc[0], x1=merged_history['date'].iloc[-1],
                    #     y0=0, y1=0, line=dict(color="rgba(128,128,128,0.5)", width=1, dash="solid"),
                    #     yref="y2" # Wichtig: Bezieht sich auf die rechte Y-Achse!
                    # )

                    # # Chart anzeigen
                    # st.plotly_chart(fig, use_container_width=True)