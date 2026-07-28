"""Married Put backtest — time-travel exit simulation.

Pure computation layer (no Streamlit / no framework), ported from
pages/backtesting/married_put_backtesting.py so it can be reused by the
FastAPI endpoint. Given an entry date, a comparison (exit) date and the
original trade parameters, it computes the simulated exit value, P&L,
ROI, annualized ROI and the stock/option price series for charting.
"""

from datetime import datetime

from src.database import select_into_dataframe

# Broker round-trip fee assumed by the original page.
ENTRY_FEE = 3.5


def parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    return value


def _price_at_date(table_hist, table_live, key_col, key_val, value_col, out_col, selected_date):
    """Return the most recent row on/at selected_date, unioning live + history."""
    if str(selected_date) == str(datetime.now().date()):
        sql = f"""
            SELECT {value_col} AS {out_col}
            FROM (
                SELECT date, {key_col}, {value_col} FROM "{table_hist}"
                WHERE {key_col} = :key_val
                UNION ALL
                SELECT CURRENT_DATE AS date, {key_col}, {value_col} FROM "{table_live}"
                WHERE {key_col} = :key_val
            ) u
            WHERE date <= :selected_date
            ORDER BY date DESC
            LIMIT 1
        """
    else:
        sql = f"""
            SELECT {value_col} AS {out_col}
            FROM "{table_hist}"
            WHERE {key_col} = :key_val AND date <= :selected_date
            ORDER BY date DESC
            LIMIT 1
        """
    return select_into_dataframe(query=sql, params={"key_val": key_val, "selected_date": selected_date})


def get_option_price_at_date(option_osi, selected_date):
    return _price_at_date(
        "OptionDataMassiveHistory", "OptionDataMassive",
        "option_osi", option_osi, "day_close", "premium_option_price", selected_date,
    )


def get_stock_price_at_date(symbol, selected_date):
    return _price_at_date(
        "StockPricesYahooHistory", "StockPricesYahoo",
        "symbol", symbol, "close", "close_price", selected_date,
    )


def get_dividends_between_dates(symbol, from_date, to_date):
    sql = """
        SELECT COALESCE(SUM(dividends), 0) AS dividend_sum
        FROM "StockPricesYahooHistory"
        WHERE symbol = :symbol AND date > :from_date AND date <= :to_date
    """
    df = select_into_dataframe(query=sql, params={"symbol": symbol, "from_date": from_date, "to_date": to_date})
    if df.empty:
        return 0.0
    return float(df.iloc[0]["dividend_sum"] or 0.0)


def get_stock_range(symbol, from_date, to_date):
    sql = """
        SELECT date, close AS close_price
        FROM "StockPricesYahooHistory"
        WHERE symbol = :symbol AND date BETWEEN :from_date AND :to_date
        ORDER BY date ASC
    """
    return select_into_dataframe(query=sql, params={"symbol": symbol, "from_date": from_date, "to_date": to_date})


def get_option_range(option_osi, from_date, to_date):
    sql = """
        SELECT date, day_close AS premium_option_price
        FROM "OptionDataMassiveHistory"
        WHERE option_osi = :option_osi AND date BETWEEN :from_date AND :to_date
        ORDER BY date ASC
    """
    return select_into_dataframe(query=sql, params={"option_osi": option_osi, "from_date": from_date, "to_date": to_date})


def simulate_married_put_exit(trade: dict, entry_date, compare_date) -> dict:
    """Compute the simulated exit outcome for a married put position.

    trade must contain: symbol, live_stock_price, premium_option_price,
    number_of_stocks, option_osi, strike_price, expiration_date.
    Returns a dict of metrics + the stock/option price series for charting.
    """
    initial_stock_price = float(trade["live_stock_price"])
    initial_option_price = float(trade["premium_option_price"])
    number_of_stocks = int(trade["number_of_stocks"])
    option_osi = trade.get("option_osi")
    strike_price = float(trade["strike_price"])
    expiration_date = parse_date(trade["expiration_date"])

    stock_exit_df = get_stock_price_at_date(trade["symbol"], compare_date)
    if stock_exit_df is None or stock_exit_df.empty:
        return {"error": "no_stock_data", "message": "Kein Kursverlauf für das Vergleichsdatum verfügbar."}

    stock_exit_price = float(stock_exit_df.iloc[0]["close_price"])

    option_exit_df = get_option_price_at_date(option_osi, compare_date) if option_osi else None
    option_exit_price = (
        float(option_exit_df.iloc[0]["premium_option_price"])
        if option_exit_df is not None and not option_exit_df.empty
        else None
    )

    cmp_d = parse_date(compare_date)
    after_expiration = cmp_d > expiration_date

    if not after_expiration and option_exit_price is not None:
        option_value_end = option_exit_price * number_of_stocks
        option_exit_kind = "premium"
        option_exit_unit = option_exit_price
    else:
        option_intrinsic = max(0.0, strike_price - stock_exit_price)
        option_value_end = option_intrinsic * number_of_stocks
        option_exit_kind = "intrinsic"
        option_exit_unit = option_intrinsic

    dividends_paid_total = get_dividends_between_dates(trade["symbol"], entry_date, compare_date) * number_of_stocks

    investment_start = number_of_stocks * (initial_stock_price + initial_option_price) + ENTRY_FEE
    closing_stock_value = stock_exit_price * number_of_stocks
    total_end_value = closing_stock_value + option_value_end + dividends_paid_total
    profit = total_end_value - investment_start
    days_held = (cmp_d - parse_date(entry_date)).days
    roi_pct = profit / investment_start * 100 if investment_start else 0.0
    roi_annualized_pct = (
        profit / investment_start * 365.0 / days_held * 100
        if investment_start and days_held > 0 else None
    )
    stock_change_pct = (stock_exit_price / initial_stock_price - 1) * 100 if initial_stock_price else 0.0
    option_change_pct = (
        (option_exit_price / initial_option_price - 1) * 100
        if (option_exit_price is not None and initial_option_price and not after_expiration) else None
    )

    # Chart series
    stock_range = get_stock_range(trade["symbol"], entry_date, compare_date)
    option_range = get_option_range(option_osi, entry_date, compare_date) if option_osi else None
    stock_series = (
        [{"date": str(r["date"]), "close": float(r["close_price"])} for _, r in stock_range.iterrows()]
        if stock_range is not None and not stock_range.empty else []
    )
    option_series = (
        [{"date": str(r["date"]), "premium": float(r["premium_option_price"])} for _, r in option_range.iterrows()]
        if option_range is not None and not option_range.empty else []
    )

    breakeven = initial_stock_price + initial_option_price

    return {
        "entry_date": str(entry_date),
        "compare_date": str(compare_date),
        "expiration_date": str(expiration_date),
        "after_expiration": after_expiration,
        "initial_stock_price": round(initial_stock_price, 2),
        "initial_option_price": round(initial_option_price, 2),
        "number_of_stocks": number_of_stocks,
        "strike_price": round(strike_price, 2),
        "breakeven": round(breakeven, 2),
        "stock_exit_price": round(stock_exit_price, 2),
        "option_exit_kind": option_exit_kind,
        "option_exit_unit": round(option_exit_unit, 2),
        "investment_start": round(investment_start, 2),
        "total_end_value": round(total_end_value, 2),
        "dividends_paid_total": round(dividends_paid_total, 2),
        "profit": round(profit, 2),
        "days_held": days_held,
        "roi_pct": round(roi_pct, 2),
        "roi_annualized_pct": round(roi_annualized_pct, 2) if roi_annualized_pct is not None else None,
        "stock_change_pct": round(stock_change_pct, 2),
        "option_change_pct": round(option_change_pct, 2) if option_change_pct is not None else None,
        "stock_series": stock_series,
        "option_series": option_series,
    }
