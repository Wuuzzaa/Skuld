"""RSL Momentum Rotation backtest — portfolio simulation engine.

Pure computation layer (no Streamlit / no framework), ported from
pages/backtesting/rsl_momentum_backtesting.py so it can be reused by the
FastAPI endpoint. The day-by-day rebalancing simulation, sector limits,
fees, taxes and percentile-exit logic are unchanged from the master page;
only the Streamlit UI has been stripped out. The KPI computations (CAGR,
Sharpe, volatility, max drawdown) that lived in the Streamlit display
function are reproduced here 1:1 so the endpoint can return them directly.
"""

from concurrent.futures import ThreadPoolExecutor
import logging
import os
import pandas as pd
import numpy as np
from datetime import datetime, date
import time

from src.data_aging import is_weekend
from src.database import select_into_dataframe

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


def _calculate_avg_holding_days(df_trades, end_date):
    """Average holding days across positions, treating open ones as closed at end_date.

    Ported verbatim from the Streamlit display helper.
    """
    if df_trades.empty:
        return 0.0
    buys = {}
    durations = []
    for _, row in df_trades.iterrows():
        sym = row['symbol']
        d = parse_date(row['date'])
        t_type = row['type']
        if t_type == 'BUY':
            if sym not in buys:
                buys[sym] = []
            buys[sym].append(d)
        elif t_type in ['SELL', 'EXIT']:
            if sym in buys and buys[sym]:
                buy_date = buys[sym].pop(0)
                durations.append((d - buy_date).days)
    # Treat remaining open positions as virtually closed at end_date
    end_date_parsed = parse_date(end_date)
    for sym, buy_dates in buys.items():
        for buy_date in buy_dates:
            durations.append((end_date_parsed - buy_date).days)
    if durations:
        return float(np.mean(durations))
    return 0.0


def _run_simulation(start_date, end_date, start_budget, flat_fee, pct_fee, top_n,
                    max_per_sector, exit_percentile, trading_frequency,
                    allow_fractional, risk_free_rate, tax_rate):
    """Core portfolio simulation. Returns (df_port, df_trades) or None.

    This is the master simulation logic, unchanged except that the Streamlit
    call sites have been removed. Data access, rebalancing, sector limits,
    fees, taxes and percentile-exit behaviour are identical to master.
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

        if df_history is None:
            return None

        # Merge profiles
        df_history = df_history.merge(df_profiles, on='symbol', how='left')
        df_history['snapshot_date'] = pd.to_datetime(df_history['snapshot_date']).dt.date

        # Vectorized rank and percentile calculations per snapshot date
        df_history = df_history.sort_values(by=['snapshot_date', 'symbol']).reset_index(drop=True)
        df_history['rank'] = df_history.groupby('snapshot_date')['rsl'].rank(ascending=False, method='first')
        counts = df_history.groupby('snapshot_date')['symbol'].transform('count')
        df_history['percentile'] = ((counts - df_history['rank'] + 1) / counts * 100).round(1)
        df_history['above_threshold'] = df_history['percentile'] >= (100 - exit_percentile)

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
        else:  # daily
            rebalance_dates = set(trading_dates)

        # Build dictionary of prices and info for fast lookup
        # {date: {symbol: row_dict}}
        data_by_date = {}
        for date_grp, grp in df_history.groupby('snapshot_date'):
            data_by_date[date_grp] = grp.set_index('symbol').to_dict(orient='index')

        # Backtest simulation
        start_sim = time.time()
        cash = start_budget
        current_positions = {}  # {symbol: {shares, entry_price, entry_date, last_price, sector, company_name}}
        portfolio_history = []
        trades = []

        for idx, d in enumerate(trading_dates):
            day_data = data_by_date.get(d, {})
            is_last_day = (idx == len(trading_dates) - 1)

            # 1. Berechne Bruttowert und latenten Nettowert der aktuellen Positionen
            pos_value_gross = 0.0
            pos_value_net = 0.0

            for sym, pos in current_positions.items():
                price = day_data.get(sym, {}).get('price', pos['last_price'])
                pos['last_price'] = price

                gross_val = pos['shares'] * price
                pos_value_gross += gross_val

                profit = (price - pos['entry_price']) * pos['shares']
                tax = max(0.0, profit * tax_rate)
                pos_value_net += (gross_val - tax)

            current_total_value = cash + (pos_value_net if is_last_day else pos_value_gross)

            portfolio_history.append({
                'date': d,
                'cash': cash,
                'positions_value': pos_value_gross if not is_last_day else pos_value_net,
                'total_value': current_total_value
            })

            # Fiktive Endverkäufe am letzten Tag ins Logbuch aufnehmen
            if is_last_day:
                for sym, pos in list(current_positions.items()):
                    sell_price = day_data.get(sym, {}).get('price', pos['last_price'])
                    revenue = pos['shares'] * sell_price
                    fee = flat_fee + revenue * pct_fee

                    gross_profit = (sell_price - pos['entry_price']) * pos['shares']
                    realized_tax = max(0.0, gross_profit * tax_rate)
                    cash_flow = revenue - fee - realized_tax

                    profit_pct = (gross_profit / (pos['entry_price'] * pos['shares']) * 100.0) if pos['entry_price'] > 0 else 0.0

                    trades.append({
                        'date': d,
                        'type': 'EXIT',
                        'symbol': sym,
                        'company_name': f"{pos['company_name']} (Offene Position aufgelöst)",
                        'sector': pos['sector'],
                        'shares': pos['shares'],
                        'price': sell_price,
                        'value': revenue,
                        'fee': fee,
                        'tax': realized_tax,
                        'profit_abs': gross_profit,
                        'profit_pct': profit_pct,
                        'cash_flow': cash_flow
                    })
                # Positionen leeren, damit sie nicht doppelt zählen
                current_positions.clear()

            # Rebalancing (nur an regulären Rebalancing-Tagen und NICHT am letzten Tag)
            if d in rebalance_dates and not is_last_day:
                exited_symbols = []
                for sym, pos in list(current_positions.items()):
                    if sym not in day_data:
                        # Missing from current snapshot (delisted/no data) -> exit!
                        exited_symbols.append(sym)
                    else:
                        above = day_data[sym]['above_threshold']
                        if not above:
                            exited_symbols.append(sym)

                # Verkäufe ausführen
                for sym in exited_symbols:
                    pos = current_positions.pop(sym)
                    sell_price = day_data.get(sym, {}).get('price', pos['last_price'])
                    revenue = pos['shares'] * sell_price
                    fee = flat_fee + revenue * pct_fee

                    gross_profit = (sell_price - pos['entry_price']) * pos['shares']
                    realized_tax = max(0.0, gross_profit * tax_rate)
                    cash_flow = revenue - fee - realized_tax
                    cash += cash_flow

                    profit_pct = (gross_profit / (pos['entry_price'] * pos['shares']) * 100.0) if pos['entry_price'] > 0 else 0.0

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
                        'tax': realized_tax,
                        'profit_abs': gross_profit,
                        'profit_pct': profit_pct,
                        'cash_flow': cash_flow
                    })

                # Käufe ausführen
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
                                'tax': 0.0,
                                'profit_abs': 0.0,
                                'profit_pct': 0.0,
                                'cash_flow': -(cost + fee)
                            })
        logger.info(f"Simulation completed in {round(time.time() - start_sim, 2)}s.")

        df_port = pd.DataFrame(portfolio_history)
        df_trades = pd.DataFrame(trades)

        if df_spy is not None and not df_spy.empty:
            df_spy['snapshot_date'] = pd.to_datetime(df_spy['snapshot_date']).dt.date
            df_port['date'] = pd.to_datetime(df_port['date']).dt.date
            df_merged = df_port.merge(df_spy, left_on='date', right_on='snapshot_date', how='left')
            # Fill missing SPY values if any
            df_merged['price'] = df_merged['price'].ffill().bfill()

            # Calculate benchmark capital starting at the same start_budget
            if not df_merged['price'].empty and df_merged['price'].iloc[0] > 0:
                spy_start = df_merged['price'].iloc[0]
                shares = start_budget / spy_start

                spy_values = shares * df_merged['price']
                spy_final_gross = spy_values.iloc[-1]
                spy_profit = spy_final_gross - start_budget
                spy_tax = max(0.0, spy_profit * tax_rate)

                spy_values_adjusted = spy_values.copy()
                spy_values_adjusted.iloc[-1] = spy_final_gross - spy_tax

                df_merged['spy_benchmark'] = spy_values_adjusted
            else:
                df_merged['spy_benchmark'] = start_budget

            df_port = df_merged.drop(columns=['snapshot_date', 'price']).rename(columns={'spy_benchmark': 'spy_value'})
        else:
            df_port['spy_value'] = start_budget

        logger.info(f"Calculate RSL Momentum Strategy in {round(time.time() - start_calculate_rsl_momentum_strategy, 2)}s.")
        return df_port, df_trades


def calculate_rsl_momentum_strategy(start_date, end_date, start_budget=10000.0,
                                    flat_fee=4.90, pct_fee=0.001, top_n=5,
                                    max_per_sector=2, exit_percentile=50.0,
                                    trading_frequency='weekly', allow_fractional=False,
                                    risk_free_rate=0.0, tax_rate=0.25):
    """
    Simulate RSL Momentum rotation strategy backtest from start_date to end_date.

    Returns a structured dict with summary KPIs, the equity curve and the
    transaction log. Returns None if no data is available for the period.
    The KPI formulas (CAGR, Sharpe, volatility, max drawdown) are the same
    ones the master Streamlit page computed for its metric tiles.
    """
    res = _run_simulation(
        start_date=start_date,
        end_date=end_date,
        start_budget=start_budget,
        flat_fee=flat_fee,
        pct_fee=pct_fee,
        top_n=top_n,
        max_per_sector=max_per_sector,
        exit_percentile=exit_percentile,
        trading_frequency=trading_frequency,
        allow_fractional=allow_fractional,
        risk_free_rate=risk_free_rate,
        tax_rate=tax_rate,
    )

    if res is None:
        return None

    df_port, df_trades = res

    if df_port is None or df_port.empty:
        return None

    # --- KPIs (identical formulas to the master display function) ---
    final_capital = float(df_port['total_value'].iloc[-1])
    total_return_pct = (final_capital - start_budget) / start_budget * 100.0

    # CAGR (calendar-day based)
    calendar_days = (parse_date(end_date) - parse_date(start_date)).days
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
    max_dd_pct = float(drawdowns.min() * 100.0) if not drawdowns.empty else 0.0

    # SPY benchmark performance
    final_spy = float(df_port['spy_value'].iloc[-1])
    spy_return_pct = (final_spy - start_budget) / start_budget * 100.0
    spy_cagr_pct = ((final_spy / start_budget) ** (365.0 / calendar_days) - 1) * 100.0 if calendar_days > 0 else 0.0

    # Average holding duration
    avg_holding_days = _calculate_avg_holding_days(df_trades, end_date)

    # NaN-safe scalar helper for JSON serialization
    def _num(x):
        try:
            xf = float(x)
        except (TypeError, ValueError):
            return None
        if pd.isna(xf):
            return None
        return xf

    summary = {
        "end_capital": _num(final_capital),
        "cagr": _num(cagr_pct),
        "sharpe": _num(sharpe),
        "volatility": _num(volatility_pct),
        "max_drawdown": _num(max_dd_pct),
        "total_return_pct": _num(total_return_pct),
        "start_budget": _num(start_budget),
        "days": calendar_days,
        "num_trades": int(len(df_trades)),
        "avg_holding_days": _num(avg_holding_days),
        "spy_end_capital": _num(final_spy),
        "spy_return_pct": _num(spy_return_pct),
        "spy_cagr": _num(spy_cagr_pct),
    }

    equity_curve = [
        {
            "date": str(row["date"]),
            "portfolio_value": _num(row["total_value"]),
            "spy_value": _num(row["spy_value"]),
        }
        for _, row in df_port.iterrows()
    ]

    if df_trades.empty:
        transactions = []
    else:
        transactions = [
            {
                "date": str(row["date"]),
                "action": row["type"],
                "symbol": row["symbol"],
                "company_name": row["company_name"],
                "sector": row["sector"],
                "shares": _num(row["shares"]),
                "price": _num(row["price"]),
                "value": _num(row["value"]),
                "fee": _num(row["fee"]),
                "tax": _num(row["tax"]),
                "profit_abs": _num(row["profit_abs"]),
                "profit_pct": _num(row["profit_pct"]),
                "cash_flow": _num(row["cash_flow"]),
            }
            for _, row in df_trades.iterrows()
        ]

    return {
        "summary": summary,
        "equity_curve": equity_curve,
        "transactions": transactions,
    }
