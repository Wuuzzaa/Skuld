"""Vertical spread backtest — time-travel exit simulation.

Pure computation layer ported from pages/backtesting/spreads_backtesting.py.
Handles two-leg (short + long) vertical spreads: computes initial credit,
closing debit, P&L, capital at risk (BPR), ROI-on-risk and annualized ROI,
plus the stock/leg price series for charting. Entry prices come from the
originating spread row; exit prices are read from history at the comparison
date. An optional manual override lets the caller supply real fill prices and
fees. A live-quote path (yahooquery) is available but off by default.
"""

from datetime import datetime

from src.database import select_into_dataframe

CONTRACT_SIZE = 100


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    return value


def _option_price_at_date(option_osi, selected_date):
    if str(selected_date) == str(datetime.now().date()):
        sql = """
            SELECT day_close AS premium_option_price, close AS stock_close
            FROM (
                SELECT date, option_osi, day_close, close FROM "OptionDataMassiveHistory" oh
                    JOIN "StockPricesYahooHistory" sh USING (symbol, date)
                WHERE option_osi = :osi
                UNION ALL
                SELECT CURRENT_DATE AS date, option_osi, day_close, s.close
                    FROM "OptionDataMassive" o JOIN "StockPricesYahoo" s USING (symbol)
                WHERE option_osi = :osi
            ) u
            WHERE date <= :selected_date
            ORDER BY date DESC LIMIT 1
        """
    else:
        sql = """
            SELECT oh.day_close AS premium_option_price, sh.close AS stock_close
            FROM "OptionDataMassiveHistory" oh
                JOIN "StockPricesYahooHistory" sh USING (symbol, date)
            WHERE oh.option_osi = :osi AND oh.date <= :selected_date
            ORDER BY oh.date DESC LIMIT 1
        """
    return select_into_dataframe(query=sql, params={"osi": option_osi, "selected_date": selected_date})


def _option_range(option_osi, from_date, to_date):
    sql = """
        SELECT date, day_close AS premium_option_price
        FROM "OptionDataMassiveHistory"
        WHERE option_osi = :osi AND date BETWEEN :from_date AND :to_date
        ORDER BY date ASC
    """
    return select_into_dataframe(query=sql, params={"osi": option_osi, "from_date": from_date, "to_date": to_date})


def _stock_range(symbol, from_date, to_date):
    sql = """
        SELECT date, close AS close_price
        FROM "StockPricesYahooHistory"
        WHERE symbol = :symbol AND date BETWEEN :from_date AND :to_date
        ORDER BY date ASC
    """
    return select_into_dataframe(query=sql, params={"symbol": symbol, "from_date": from_date, "to_date": to_date})


def simulate_spread_exit(spread: dict, entry_date, compare_date, override: dict | None = None) -> dict:
    """Simulate exiting a vertical spread at compare_date.

    spread must contain: symbol, sell_option_osi, buy_option_osi, sell_strike,
    buy_strike, sell_last_option_price, buy_last_option_price, expiration_date.
    override (optional) may supply: entry_sell_price, entry_buy_price,
    exit_sell_price, exit_buy_price, start_transaction_cost, exit_transaction_cost.
    """
    override = override or {}
    expiration_date = parse_date(spread["expiration_date"])
    cmp_d = parse_date(compare_date)

    strike_sell = float(spread["sell_strike"])
    strike_buy = float(spread["buy_strike"])
    spread_width = abs(strike_sell - strike_buy)

    # Entry prices: from the originating row unless overridden.
    entry_sell_price = float(override.get("entry_sell_price", spread["sell_last_option_price"]))
    entry_buy_price = float(override.get("entry_buy_price", spread["buy_last_option_price"]))
    start_fee = float(override.get("start_transaction_cost", 0.0))
    exit_fee = float(override.get("exit_transaction_cost", 0.0))

    # Exit prices: overridden, or read from history at the comparison date.
    if "exit_sell_price" in override and "exit_buy_price" in override:
        exit_sell_price = float(override["exit_sell_price"])
        exit_buy_price = float(override["exit_buy_price"])
    else:
        sell_exit = _option_price_at_date(spread["sell_option_osi"], compare_date)
        buy_exit = _option_price_at_date(spread["buy_option_osi"], compare_date)
        if sell_exit is None or buy_exit is None or sell_exit.empty or buy_exit.empty:
            return {"error": "no_option_data", "message": "Die Option konnte für das Vergleichsdatum nicht geladen werden."}
        exit_sell_price = float(sell_exit.iloc[0]["premium_option_price"])
        exit_buy_price = float(buy_exit.iloc[0]["premium_option_price"])

    # After expiration the position is closed at zero remaining option debit.
    after_expiration = cmp_d >= expiration_date
    if after_expiration:
        exit_sell_price = 0.0
        exit_buy_price = 0.0

    initial_cash_flow = (entry_sell_price - entry_buy_price) * CONTRACT_SIZE - start_fee
    close_cash_flow = (exit_buy_price - exit_sell_price) * CONTRACT_SIZE - exit_fee
    profit = initial_cash_flow + close_cash_flow

    if initial_cash_flow > 0:
        bpr_capital = spread_width * CONTRACT_SIZE - initial_cash_flow
    else:
        bpr_capital = abs(initial_cash_flow)

    roi_pct = (profit / bpr_capital * 100) if bpr_capital > 0 else None
    max_profit_pct = (profit / initial_cash_flow * 100) if initial_cash_flow else None
    days_held = (cmp_d - parse_date(entry_date)).days
    roi_annualized_pct = (roi_pct * 365.0 / days_held) if (roi_pct is not None and days_held > 0) else None

    # Chart series (stock + both legs)
    stock_range = _stock_range(spread["symbol"], entry_date, compare_date)
    sell_range = _option_range(spread["sell_option_osi"], entry_date, compare_date)
    buy_range = _option_range(spread["buy_option_osi"], entry_date, compare_date)

    def _series(df, col, out):
        return [{"date": str(r["date"]), out: float(r[col])} for _, r in df.iterrows()] if df is not None and not df.empty else []

    return {
        "entry_date": str(entry_date),
        "compare_date": str(compare_date),
        "expiration_date": str(expiration_date),
        "after_expiration": after_expiration,
        "strike_sell": round(strike_sell, 2),
        "strike_buy": round(strike_buy, 2),
        "spread_width": round(spread_width, 2),
        "entry_sell_price": round(entry_sell_price, 2),
        "entry_buy_price": round(entry_buy_price, 2),
        "exit_sell_price": round(exit_sell_price, 2),
        "exit_buy_price": round(exit_buy_price, 2),
        "initial_cash_flow": round(initial_cash_flow, 2),
        "close_cash_flow": round(close_cash_flow, 2),
        "profit": round(profit, 2),
        "bpr_capital": round(bpr_capital, 2),
        "roi_pct": round(roi_pct, 2) if roi_pct is not None else None,
        "max_profit_pct": round(max_profit_pct, 2) if max_profit_pct is not None else None,
        "roi_annualized_pct": round(roi_annualized_pct, 2) if roi_annualized_pct is not None else None,
        "days_held": days_held,
        "stock_series": _series(stock_range, "close_price", "close"),
        "sell_leg_series": _series(sell_range, "premium_option_price", "premium"),
        "buy_leg_series": _series(buy_range, "premium_option_price", "premium"),
    }
