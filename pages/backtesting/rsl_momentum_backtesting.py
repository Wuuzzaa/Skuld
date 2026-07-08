from concurrent.futures import ThreadPoolExecutor
import logging
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date
import time

from src.data_aging import is_weekend
from src.database import select_into_dataframe
from src.streamlit_helpers import render_date_filter

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

def get_profiles():
    """
    Fetch S&P 500 constituents profile data for sector diversification.
    """
    df_profiles = select_into_dataframe("""
        SELECT symbol, name as company_name, sector 
        FROM "StockAssetProfilesYahoo"
        WHERE symbol IN (
                SELECT symbol 
                FROM "StockSP500ConstituentsHistorical"
            )
    """)
    return df_profiles

def get_rsl_history(start_date, end_date):
    """
    Fetch RSL history for S&P 500 constituents between start_date and end_date.
    """
    if str(start_date) == str(time.strftime("%Y-%m-%d", time.gmtime())) and not is_weekend():
        sql_history = """
            SELECT
                T.SNAPSHOT_DATE,
                T.SYMBOL,
                T."RSL" as rsl,
                P.CLOSE AS PRICE
            FROM
                "TechnicalIndicatorsCalculatedHistoryDaily" T
                JOIN "StockPricesYahooHistoryDaily" P 
                    ON T.SNAPSHOT_DATE = P.SNAPSHOT_DATE AND T.SYMBOL = P.SYMBOL
                JOIN "StockSP500ConstituentsHistorical" AS SP 
                    ON T.SYMBOL = SP.SYMBOL
            WHERE
                T.SNAPSHOT_DATE BETWEEN :start_date AND :end_date AND T.SNAPSHOT_DATE <> CURRENT_DATE
                AND P.SNAPSHOT_DATE BETWEEN :start_date AND :end_date  AND P.SNAPSHOT_DATE <> CURRENT_DATE
                AND (SP.DATE_ADDED <= T.SNAPSHOT_DATE OR SP.DATE_ADDED IS NULL)
                AND (SP.DATE_REMOVED > T.SNAPSHOT_DATE OR SP.DATE_REMOVED IS NULL)
            UNION ALL
            SELECT
                CURRENT_DATE AS SNAPSHOT_DATE,
                T.SYMBOL,
                T."RSL" as rsl,
                P.CLOSE AS PRICE
            FROM
                "TechnicalIndicatorsCalculated" T
                JOIN "StockPricesYahoo" P 
                    ON T.SYMBOL = P.SYMBOL
                JOIN "StockSP500ConstituentsHistorical" AS SP 
                    ON T.SYMBOL = SP.SYMBOL
            WHERE (SP.DATE_ADDED <= CURRENT_DATE OR SP.DATE_ADDED IS NULL)
                AND (SP.DATE_REMOVED > CURRENT_DATE OR SP.DATE_REMOVED IS NULL);
        """

        # sql_history = """
        #     WITH historical_sp500_prices AS (
        #         SELECT
        #             P.SNAPSHOT_DATE,
        #             P.SYMBOL,
        #             P.CLOSE
        #         FROM
        #             "StockSP500ConstituentsHistorical" AS SP
        #             JOIN "StockPricesYahooHistoryDaily" P 
        #                 ON P.SYMBOL = SP.SYMBOL
        #         WHERE
        #             P.SNAPSHOT_DATE BETWEEN :start_date AND :end_date AND P.SNAPSHOT_DATE <> CURRENT_DATE
        #             AND (SP.DATE_ADDED <= P.SNAPSHOT_DATE OR SP.DATE_ADDED IS NULL)
        #             AND (SP.DATE_REMOVED > P.SNAPSHOT_DATE OR SP.DATE_REMOVED IS NULL)
        #     )
        #     SELECT
        #         H.SNAPSHOT_DATE,
        #         H.SYMBOL,
        #         T."RSL" as rsl,
        #         H.CLOSE AS PRICE
        #     FROM
        #         "TechnicalIndicatorsCalculatedHistoryDaily" T
        #         -- Wir joinen das CTE als INNER JOIN. Da Postgres meist die rechte/kleinere Seite 
        #         -- in den Hash packt, zwingen wir es hier zum Streaming der großen Indikatoren-Tabelle.
        #         JOIN historical_sp500_prices H
        #             ON T.SNAPSHOT_DATE = H.SNAPSHOT_DATE AND T.SYMBOL = H.SYMBOL
        #         WHERE t.SNAPSHOT_DATE BETWEEN :start_date AND :end_date AND t.SNAPSHOT_DATE <> CURRENT_DATE

        #     UNION ALL

        #     SELECT
        #         CURRENT_DATE AS SNAPSHOT_DATE,
        #         T.SYMBOL,
        #         T."RSL" as rsl,
        #         P.CLOSE AS PRICE
        #     FROM
        #         "TechnicalIndicatorsCalculated" T
        #         JOIN "StockPricesYahoo" P 
        #             ON T.SYMBOL = P.SYMBOL
        #         JOIN "StockSP500ConstituentsHistorical" AS SP 
        #             ON T.SYMBOL = SP.SYMBOL
        #     WHERE (SP.DATE_ADDED <= CURRENT_DATE OR SP.DATE_ADDED IS NULL)
        #         AND (SP.DATE_REMOVED > CURRENT_DATE OR SP.DATE_REMOVED IS NULL);
        # """
    else:
        sql_history = """
            SELECT 
                t.snapshot_date,
                t.symbol,
                t."RSL" as rsl,
                p.close as price
            FROM "TechnicalIndicatorsCalculatedHistoryDaily" t
            JOIN "StockPricesYahooHistoryDaily" p 
                ON t.snapshot_date = p.snapshot_date AND t.symbol = p.symbol
            JOIN "StockSP500ConstituentsHistorical" as sp
            ON t.symbol = sp.symbol
            WHERE 
              T.SNAPSHOT_DATE BETWEEN :start_date AND :end_date
              AND P.SNAPSHOT_DATE BETWEEN :start_date AND :end_date
              -- check if the symbol was in the S&P 500 at the time of the snapshot
              AND (date_added <= t.snapshot_date OR date_added IS NULL)
              AND (date_removed > t.snapshot_date OR date_removed IS NULL)
        """
         
    df_history = select_into_dataframe(sql_history, params={
        "start_date": start_date, 
        "end_date": end_date
    })
    
    if df_history.empty:
        logger.info("No historical data available.")
        return None
    
    return df_history

def get_spy_history(start_date, end_date):
    """
    Fetch SPY benchmark data for the given date range.
    """
    # 3. S&P 500 Buy & Hold benchmark query
    if str(start_date) == str(time.strftime("%Y-%m-%d", time.gmtime())) and not is_weekend():
        sql_spy = """
            SELECT snapshot_date, close as price
            FROM "StockPricesYahooHistoryDaily"
            WHERE symbol = 'SPY'
            AND snapshot_date <> CURRENT_DATE
            AND snapshot_date BETWEEN :start_date AND :end_date
            UNION ALL
            SELECT CURRENT_DATE as snapshot_date, close as price
            FROM "StockPricesYahoo"
            WHERE symbol = 'SPY'
            ORDER BY snapshot_date ASC
        """
    else:
        sql_spy = """
            SELECT snapshot_date, close as price
            FROM "StockPricesYahooHistoryDaily"
            WHERE symbol = 'SPY'
              AND snapshot_date BETWEEN :start_date AND :end_date
            ORDER BY snapshot_date ASC
        """
        
    df_spy = select_into_dataframe(sql_spy, params={
        "start_date": start_date, 
        "end_date": end_date
    })
    
    if df_spy.empty:
        logger.info("No SPY benchmark data available.")
        return None
    
    return df_spy

def calculate_rsl_momentum_strategy(start_date, end_date, start_budget=10000.0, 
                                   flat_fee=4.90, pct_fee=0.001, top_n=5, 
                                   max_per_sector=2, exit_percentile=50.0, 
                                   trading_frequency='weekly', allow_fractional=False,
                                   risk_free_rate=0.0):
    """
    Simulate RSL Momentum rotation strategy backtest from start_date to end_date.
    """
    start_calculate_rsl_momentum_strategy = time.time()
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_profiles = executor.submit(get_profiles)
        future_history = executor.submit(get_rsl_history, start_date, end_date)
        spy_future = executor.submit(get_spy_history, start_date, end_date)
        
        # 1. Fetch S&P 500 constituents profile data for sector diversification
        df_profiles = future_profiles.result()
        # 2. Fetch history (optimized: select conditionally based on end_date)
        df_history = future_history.result()
        # 3. Fetch S&P 500 Buy & Hold benchmark data
        df_spy = spy_future.result()

        # Merge profiles
        start = time.time()
        df_history = df_history.merge(df_profiles, on='symbol', how='left')
        df_history['snapshot_date'] = pd.to_datetime(df_history['snapshot_date']).dt.date
        logger.info(f"Merge profiles in {round(time.time() - start, 2)}s.")
            
        
        # Vectorized rank and percentile calculations per snapshot date
        start = time.time()

        df_history = df_history.sort_values(by=['snapshot_date', 'symbol']).reset_index(drop=True)
        df_history['rank'] = df_history.groupby('snapshot_date')['rsl'].rank(ascending=False, method='first')
        counts = df_history.groupby('snapshot_date')['symbol'].transform('count')
        df_history['percentile'] = ((counts - df_history['rank'] + 1) / counts * 100).round(1)
        df_history['above_threshold'] = df_history['percentile'] >= (100 - exit_percentile)
        logger.info(f"Vectorized rank and percentile calculations per snapshot date in {round(time.time() - start, 2)}s.")
        
        # Sort history chronologically
        df_history = df_history.sort_values('snapshot_date')
        
        # Get unique trading dates
        trading_dates = sorted(df_history['snapshot_date'].unique())
        if not trading_dates:
            return None
            
        # Group dates based on trading frequency
        trading_dates_df = pd.DataFrame({'date': trading_dates})
        trading_dates_df['year'] = pd.to_datetime(trading_dates_df['date']).dt.year
        
        if trading_frequency == 'weekly':
            trading_dates_df['week'] = pd.to_datetime(trading_dates_df['date']).dt.isocalendar().week
            rebalance_dates = set(trading_dates_df.groupby(['year', 'week'])['date'].first())
        elif trading_frequency == 'monthly':
            trading_dates_df['month'] = pd.to_datetime(trading_dates_df['date']).dt.month
            rebalance_dates = set(trading_dates_df.groupby(['year', 'month'])['date'].first())
        else: # daily
            rebalance_dates = set(trading_dates)
            
        # Build dictionary of prices and info for fast lookup
        # {date: {symbol: row_dict}}
        data_by_date = {}
        for date_grp, grp in df_history.groupby('snapshot_date'):
            data_by_date[date_grp] = grp.set_index('symbol').to_dict(orient='index')
            
        # Backtest simulation
        start_sim = time.time()
        cash = start_budget
        current_positions = {} # {symbol: {shares, entry_price, entry_date, last_price, sector, company_name}}
        portfolio_history = []
        trades = []
        
        for idx, d in enumerate(trading_dates):
            day_data = data_by_date.get(d, {})
            
            # Calculate current portfolio value on day d
            pos_value = 0.0
            for sym, pos in current_positions.items():
                # If price is missing for this day, use last known price
                price = day_data.get(sym, {}).get('price', pos['last_price'])
                pos['last_price'] = price
                pos_value += pos['shares'] * price
                
            total_value = cash + pos_value
            portfolio_history.append({
                'date': d,
                'cash': cash,
                'positions_value': pos_value,
                'total_value': total_value
            })
            
            # Rebalancing
            if d in rebalance_dates:
                # 1. Exit positions below Top % or delisted
                exited_symbols = []
                for sym, pos in list(current_positions.items()):
                    if sym not in day_data:
                        # Missing from current snapshot (delisted/no data) -> exit!
                        exited_symbols.append(sym)
                    else:
                        above = day_data[sym]['above_threshold']
                        if not above:
                            exited_symbols.append(sym)
                
                # Execute sells
                for sym in exited_symbols:
                    pos = current_positions.pop(sym)
                    sell_price = day_data.get(sym, {}).get('price', pos['last_price'])
                    revenue = pos['shares'] * sell_price
                    fee = flat_fee + revenue * pct_fee
                    cash += revenue - fee
                    trades.append({
                        'date': d,
                        'type': 'SELL',
                        'symbol': sym,
                        'company_name': pos['company_name'],
                        'sector': pos['sector'],
                        'shares': pos['shares'],
                        'price': sell_price,
                        'value': revenue,
                        'fee': fee,
                        'cash_flow': revenue - fee
                    })
                    
                # 2. Enter new positions
                available_slots = top_n - len(current_positions)
                if available_slots > 0 and cash > 0:
                    # Count sectors in current positions
                    sector_counts = {}
                    for sym, pos in current_positions.items():
                        sec = pos['sector']
                        sector_counts[sec] = sector_counts.get(sec, 0) + 1
                        
                    # Find qualified candidates from day_data
                    candidates = []
                    day_sorted = sorted(day_data.items(), key=lambda x: x[1]['rsl'], reverse=True)
                    for sym, info in day_sorted:
                        if sym in current_positions:
                            continue
                        sec = info['sector'] or 'Unknown'
                        if sector_counts.get(sec, 0) < max_per_sector:
                            candidates.append((sym, info))
                            sector_counts[sec] = sector_counts.get(sec, 0) + 1
                            if len(candidates) >= available_slots:
                                break
                    
                    # Buy candidates
                    if candidates:
                        # Divide cash by available slots
                        cash_per_pos = cash / available_slots
                        for sym, info in candidates:
                            price = info['price']
                            if price <= 0:
                                continue
                            
                            shares_cash = cash_per_pos - flat_fee
                            if shares_cash <= 0:
                                continue
                                
                            shares = shares_cash / (price * (1 + pct_fee))
                            if not allow_fractional:
                                shares = np.floor(shares)
                                
                            if shares <= 0:
                                continue
                                
                            cost = shares * price
                            fee = flat_fee + cost * pct_fee
                            cash -= (cost + fee)
                            
                            current_positions[sym] = {
                                'shares': shares,
                                'entry_price': price,
                                'entry_date': d,
                                'last_price': price,
                                'sector': info['sector'] or 'Unknown',
                                'company_name': info['company_name'] or sym
                            }
                            
                            trades.append({
                                'date': d,
                                'type': 'BUY',
                                'symbol': sym,
                                'company_name': info['company_name'] or sym,
                                'sector': info['sector'] or 'Unknown',
                                'shares': shares,
                                'price': price,
                                'value': cost,
                                'fee': fee,
                                'cash_flow': -(cost + fee)
                            })
        logger.info(f"Simulation completed in {round(time.time() - start_sim, 2)}s.")

        # 3. S&P 500 Buy & Hold benchmark query
        df_spy = get_spy_history(start_date, end_date)
        
        # 4. Process results and align with benchmark
        df_port = pd.DataFrame(portfolio_history)
        df_trades = pd.DataFrame(trades)
        
        if not df_spy.empty:
            df_spy['snapshot_date'] = pd.to_datetime(df_spy['snapshot_date']).dt.date
            df_port['date'] = pd.to_datetime(df_port['date']).dt.date
            df_merged = df_port.merge(df_spy, left_on='date', right_on='snapshot_date', how='left')
            
            # Fill missing SPY values if any
            df_merged['price'] = df_merged['price'].ffill().bfill()
            
            # Calculate benchmark capital starting at the same start_budget
            if not df_merged['price'].empty and df_merged['price'].iloc[0] > 0:
                spy_start = df_merged['price'].iloc[0]
                shares = start_budget / spy_start
                df_merged['spy_benchmark'] = shares * df_merged['price'] # df_merged['spy_benchmark'] = start_budget * (df_merged['price'] / spy_start)
            else:
                df_merged['spy_benchmark'] = start_budget
                
            df_port = df_merged.drop(columns=['snapshot_date', 'price']).rename(columns={'spy_benchmark': 'spy_value'})
        else:
            df_port['spy_value'] = start_budget

        logger.info(f"Calculate RSL Momentum Strategy in {round(time.time() - start_calculate_rsl_momentum_strategy, 2)}s.")
        return df_port, df_trades

def display_rsl_momentum_backtesting(selected_date, top_n, max_per_sector, exit_percentile,
                                      min_rsl_threshold: float = 0.0, spy_filter_enabled: bool = False):
    st.divider()
    st.subheader("📈 Backtesting RSL Momentum Rotation")
    
    # Date query for compare/end date (same as spreads/married put)
    compare_date = render_date_filter(
        date_query=f'select date from (select DISTINCT snapshot_date AS date from "StockPricesYahooHistoryDaily" union select current_date AS date) as sub WHERE date > \'{selected_date}\' ORDER BY date DESC',
        date_label="Vergleichsdatum (Ende des Backtests):",
        date_session_key="rsl_momentum_compare_date",
        date_list_session_key="rsl_momentum_list_compare" + str(selected_date.strftime('%Y%m%d')),
        date_index=0,
    )
    
    if not compare_date:
        st.info("Bitte wähle ein gültiges Vergleichsdatum aus.")
        return
        
    if parse_date(compare_date) == parse_date(selected_date):
        st.info("Wähle ein anderes Vergleichsdatum als das Einstiegdatum.")
        return
        
    # Input parameters for Backtest
    st.markdown("### ⚙️ Backtest Parameter")
    col1, col2, col3 = st.columns(3)
    with col1:
        start_budget = st.number_input("Startkapital ($)", min_value=100.0, value=10000.0, step=1000.0, format="%.2f",
                                        help="Das anfängliche Budget für die Simulation.")
        trading_frequency = st.selectbox("Trading-Frequenz", options=['daily', 'weekly', 'monthly'], index=1,
                                         format_func=lambda x: {'daily': 'Täglich', 'weekly': 'Wöchentlich', 'monthly': 'Monatlich'}[x],
                                         help="Die Frequenz, mit der die Strategie rebalanciert wird.")
    with col2:
        flat_fee = st.number_input("Ordergebühr flat ($)", min_value=0.0, value=1.0, step=0.50, format="%.2f",
                                    help="Die feste Gebühr, die bei jedem Kauf- oder Verkaufsvorgang (Trade) anfällt.")
        pct_fee = st.number_input("Variable Gebühr (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05, format="%.2f",
                                   help="Die prozentuale Gebühr, die auf Basis des gesamten Transaktionsvolumens erhoben wird (z. B. 0.1% des Transaktionswerts).") / 100.0
    with col3:
        risk_free_rate = st.number_input("Risikofreier Zins (%)", min_value=0.0, max_value=20.0, value=3.0, step=0.5, format="%.2f",
                                          help="Der risikofreie Zins (z.B. Staatsanleihen), der als Hürde für die Berechnung der Sharpe Ratio abgezogen wird.") / 100.0
        allow_fractional = st.checkbox("Fraktionelle Anteile erlauben", value=False, 
                                        help="Erlaubt den Kauf von Bruchteilen einer Aktie. Wenn deaktiviert, wird auf ganze Anteile abgerundet.")
        
    # Trading Routine description based on frequency
    freq_desc = {
        'daily': "An jedem Handelstag",
        'weekly': "Jeden Montag (bzw. am ersten Handelstag der Woche)",
        'monthly': "Am ersten Handelstag jedes Monats"
    }[trading_frequency]
    st.info(f"💡 **Trading-Routine:** {freq_desc} werden Aktien im Portfolio überprüft. "
            f"Fällt eine Aktie unter das Exit-Percentil (raus aus den Top {exit_percentile}%), wird sie vollständig verkauft. "
            f"Freigewordene Plätze im Portfolio (bis Top N = {top_n}) werden mit den stärksten Picks (max. {max_per_sector} pro Sektor) "
            f"neu besetzt, sofern sich diese geändert haben.")

    # Helper function to calculate average holding days of positions (including open ones)
    def calculate_avg_holding_days(df_trades, end_date):
        if df_trades.empty:
            return 0.0
        buys = {}
        durations = []
        for _, row in df_trades.iterrows():
            sym = row['symbol']
            date = parse_date(row['date'])
            t_type = row['type']
            if t_type == 'BUY':
                if sym not in buys:
                    buys[sym] = []
                buys[sym].append(date)
            elif t_type == 'SELL':
                if sym in buys and buys[sym]:
                    buy_date = buys[sym].pop(0)
                    durations.append((date - buy_date).days)
        # Treat remaining open positions as virtually closed at end_date
        end_date_parsed = parse_date(end_date)
        for sym, buy_dates in buys.items():
            for buy_date in buy_dates:
                durations.append((end_date_parsed - buy_date).days)
        if durations:
            return np.mean(durations)
        return 0.0

    # Run Backtest button
    if st.button("🚀 Backtest ausführen", type="primary"):
        with st.spinner("Führe Backtest-Simulation aus..."):
            res = calculate_rsl_momentum_strategy(
                start_date=selected_date,
                end_date=compare_date,
                start_budget=start_budget,
                flat_fee=flat_fee,
                pct_fee=pct_fee,
                top_n=top_n,
                max_per_sector=max_per_sector,
                exit_percentile=exit_percentile,
                trading_frequency=trading_frequency,
                allow_fractional=allow_fractional,
                risk_free_rate=risk_free_rate
            )
            
            if res is None:
                st.error("Backtest konnte nicht berechnet werden. Möglicherweise keine Daten im Zeitraum vorhanden.")
                return
                
            df_port, df_trades = res
            
            # --- 1. Reporting / KPIs ---
            st.markdown("### 📊 Performance & Kennzahlen")
            final_capital = df_port['total_value'].iloc[-1]
            total_return_pct = (final_capital - start_budget) / start_budget * 100.0
            
            # CAGR
            calendar_days = (parse_date(compare_date) - parse_date(selected_date)).days
            cagr_pct = ((final_capital / start_budget) ** (365.0 / calendar_days) - 1) * 100.0 if calendar_days > 0 else 0.0
            
            # Sharpe
            daily_returns = df_port['total_value'].pct_change().dropna()
            excess_returns = daily_returns - (risk_free_rate / 252.0)
            std_dev = excess_returns.std()
            sharpe = (excess_returns.mean() / std_dev * np.sqrt(252.0)) if std_dev != 0 else 0.0
            
            # Volatility (annualized)
            volatility_pct = (daily_returns.std() * np.sqrt(252.0) * 100.0) if not daily_returns.empty else 0.0
            
            # Max Drawdown
            cum_max = df_port['total_value'].cummax()
            drawdowns = (df_port['total_value'] - cum_max) / cum_max
            max_dd_pct = drawdowns.min() * 100.0
            
            # SPY Performance
            final_spy = df_port['spy_value'].iloc[-1]
            spy_return_pct = (final_spy - start_budget) / start_budget * 100.0
            spy_cagr_pct = ((final_spy / start_budget) ** (365.0 / calendar_days) - 1) * 100.0 if calendar_days > 0 else 0.0
            
            # Position holding duration (average)
            avg_holding_days = calculate_avg_holding_days(df_trades, compare_date)
            
            # Display KPIs (3x3 grid)
            col_r1 = st.columns(3)
            col_r1[0].metric("Endkapital", f"${final_capital:,.2f}")
            col_r1[1].metric("Gesamtrendite", f"{total_return_pct:+.2f}%", f"Benchmark: {spy_return_pct:+.2f}%")
            col_r1[2].metric("Annualisierter Gewinn (CAGR)", f"{cagr_pct:.2f}%", f"Benchmark: {spy_cagr_pct:.2f}%")
            
            col_r2 = st.columns(3)
            col_r2[0].metric("Volatilität (annualisiert)", f"{volatility_pct:.2f}%", help="Die annualisierte Standardabweichung der täglichen Renditen des Portfolios.")
            col_r2[1].metric("Sharpe Ratio", f"{sharpe:.2f}", help="Verhältnis von Überrendite zur Volatilität. Höher ist besser.")
            col_r2[2].metric("Max. Drawdown", f"{max_dd_pct:.2f}%", help="Der maximale historische Verlust vom Höchststand zum Tiefststand.")
            
            col_r3 = st.columns(3)
            col_r3[0].metric("Backtest-Dauer", f"{calendar_days} Tage")
            col_r3[1].metric("Mittlere Haltedauer pro Position", f"{avg_holding_days:.1f} Tage" if avg_holding_days > 0 else "N/A",
                             help="Die durchschnittliche Dauer in Tagen, die eine Aktie im Portfolio gehalten wurde (inklusive offener Positionen am Ende).")
            col_r3[2].metric("Anzahl Trades", f"{len(df_trades)}", help="Die Gesamtzahl an Transaktionen (Käufe und Verkäufe zählen jeweils als ein Trade).")
            
            # --- 2. Chart: Portfolio vs Benchmark ---
            st.markdown("### 📈 Wertentwicklung")
            fig = go.Figure()
            fig.add_trace(go.Figure(go.Scatter(x=df_port['date'], y=df_port['total_value'], mode='lines', name='RSL Rotation Portfolio', line=dict(color='#9467bd', width=3))).data[0])
            fig.add_trace(go.Figure(go.Scatter(x=df_port['date'], y=df_port['spy_value'], mode='lines', name='S&P 500 Buy & Hold (SPY)', line=dict(color='#1f77b4', width=2, dash='dash'))).data[0])
            
            fig.update_layout(
                title="Portfolio-Wertentwicklung vs. S&P 500 (SPY)",
                xaxis_title="Datum",
                yaxis_title="Wert ($)",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(x=0.01, y=0.99, bgcolor="rgba(255,255,255,0.2)"),
                margin=dict(l=20, r=20, t=50, b=20)
            )
            fig.update_yaxes(gridcolor='rgba(128,128,128,0.15)')
            fig.update_xaxes(gridcolor='rgba(128,128,128,0.15)')
            
            st.plotly_chart(fig, use_container_width=True)
            
            # --- 3. Transaction Log ---
            st.markdown("### 📜 Transaktions-Logbuch")
            if not df_trades.empty:
                # Format Columns
                df_disp_trades = df_trades.copy()
                df_disp_trades['shares'] = df_disp_trades['shares'].round(2)
                df_disp_trades['price'] = df_disp_trades['price'].round(2)
                df_disp_trades['value'] = df_disp_trades['value'].round(2)
                df_disp_trades['fee'] = df_disp_trades['fee'].round(2)
                df_disp_trades['cash_flow'] = df_disp_trades['cash_flow'].round(2)
                
                # Style rows depending on BUY / SELL
                def style_trades(df):
                    def row_color(row):
                        if row["type"] == "BUY":
                            return ["background-color: #1e4620; color: white"] * len(row)
                        elif row["type"] == "SELL":
                            return ["background-color: #5c1a1a; color: white"] * len(row)
                        return [""] * len(row)
                    return df.style.apply(row_color, axis=1)
                    
                st.dataframe(style_trades(df_disp_trades), width="stretch", hide_index=True)
            else:
                st.info("Keine Transaktionen während des Backtests durchgeführt.")