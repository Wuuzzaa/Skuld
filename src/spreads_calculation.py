import pandas as pd
from config import NUM_SIMULATIONS, RANDOM_SEED, RISK_FREE_RATE, PATH_LOG_FILE
from src.decorator_log_function import log_function
from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator


def _calculate_expected_value_for_symbol(row):
    monte_carlo_simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=NUM_SIMULATIONS,
        random_seed=RANDOM_SEED,
        current_price=row['close'],
        dte=row['days_to_expiration_sell'],
        volatility=row['iv_sell'],
        risk_free_rate=RISK_FREE_RATE,
        dividend_yield=0,  # todo insert the dividend from the symbol here
    )

    options = [
        # SELL OPTION
        {
            'strike': row['strike_sell'],
            'premium': row['bid_sell'],
            'is_call': True if row['option_type'] == 'calls' else False,
            'is_long': False
        },
        # BUY OPTION
        {
            'strike': row['strike_buy'],
            'premium': row['ask_buy'],
            'is_call': True if row['option_type'] == 'calls' else False,
            'is_long': True
        }]

    expected_value = monte_carlo_simulator.calculate_expected_value(options=options)
    return expected_value

def _get_sell_options_by_delta_target(df, delta_target):
    """
    Find the sell options (put and call) per symbol
    by choosing the option with the closest delta to the delta_target.
    For puts, the delta_target is automatically inverted to match the negative delta values in the data.
    """
    # Split into puts and calls
    puts = df[df["option-type"] == "puts"].copy()
    calls = df[df["option-type"] == "calls"].copy()

    # Invert delta_target for puts because put deltas are negative in the data
    puts["delta_diff"] = (puts["delta"] - (-delta_target)).abs()
    calls["delta_diff"] = (calls["delta"] - delta_target).abs()

    # Find the best matching option (smallest delta_diff) per symbol
    sell_puts = puts.loc[puts.groupby("symbol")["delta_diff"].idxmin().dropna()]
    sell_calls = calls.loc[calls.groupby("symbol")["delta_diff"].idxmin().dropna()]

    return sell_puts, sell_calls


def _add_buy_options(df, sell_puts, sell_calls, spread_width):
    """
    Find the long options based on the short options and spread width.

    For puts: strike = sell_strike - spread_width
    For calls: strike = sell_strike + spread_width

    :return: put_spreads, call_spreads both pandas dataframes
    """
    #todo only perfect matching strike +- spread_width is selected.

    # Merge for puts
    puts = df[df["option-type"] == "puts"].copy()

    put_spreads = sell_puts.merge(
        puts,
        how="left",
        left_on=["symbol", "close", sell_puts["strike"] - spread_width],
        right_on=["symbol", "close", "strike"],
        suffixes=("_sell", "_buy")
    )

    # Merge for calls
    calls = df[df["option-type"] == "calls"].copy()

    call_spreads = sell_calls.merge(
        calls,
        how="left",
        left_on=["symbol", "close", sell_calls["strike"] + spread_width],
        right_on=["symbol", "close", "strike"],
        suffixes=("_sell", "_buy")
    )

    return put_spreads, call_spreads

@log_function
def calc_spreads(df:pd.DataFrame, delta_target:float, spread_width:float):
    """
    Workflow:
    - select the sell options via delta
    - select the buy options via puts and spread width
    - calculate the spread

    :param df:
    :param delta_target:
    :param spread_width:
    :return:
    """
    # sell options
    sell_puts, sell_calls = _get_sell_options_by_delta_target(df, delta_target)

    # add buy options
    puts, calls = _add_buy_options(df, sell_puts, sell_calls, spread_width)

    # merge puts and calls
    assert list(puts.columns) == list(calls.columns), "Columns of puts and calls do not match!"

    spreads = pd.concat([puts, calls], ignore_index=True)

    # clear memory
    del puts, calls, sell_puts, sell_calls

    # remove all symbols without matching buy strike. the calculations would make no sense at all.
    spreads = spreads.dropna(subset=['strike_buy'])

    # spread values calculation
    spreads["earnings_date"] = spreads['earnings_date_sell']
    spreads['option_type'] = spreads['option-type_sell']
    spreads["spread_width"] = abs(spreads['strike_sell'] - spreads['strike_buy'])
    spreads["max_profit"] = 100 * (spreads["bid_sell"] - spreads["ask_buy"])
    spreads["bpr"] = spreads["spread_width"] * 100 - spreads["max_profit"]
    spreads["profit_to_bpr"] = spreads["max_profit"] / spreads["bpr"]
    spreads["spread_theta"] = spreads["theta_sell"] - spreads["theta_buy"]
    spreads["expected_value"] = spreads.apply(_calculate_expected_value_for_symbol, axis=1)

    # Konvertiere Datums-Felder zu datetime
    spreads['earnings_date_sell'] = pd.to_datetime(spreads['earnings_date_sell'], errors='coerce')
    spreads['expiration_date_sell'] = pd.to_datetime(spreads['expiration_date_sell'], errors='coerce')

    # earnings warninng
    spreads['earnings_warning'] = spreads.apply(_earnings_warning, axis=1)

    # remove unnecessary columns for streamlit data view
    spreads_columns = [
        'symbol',
        'earnings_date',
        'earnings_warning',
        'close',
        'option_type',
        'strike_sell',
        'bid_sell',
        'delta_sell',
        'iv_sell',
        'strike_buy',
        'ask_buy',
        'delta_buy',
        'max_profit',
        'bpr',
        'profit_to_bpr',
        'spread_theta',
        "expected_value",
    ]

    return spreads[spreads_columns]

# Add earnings warning column. Warning for 7 days or less before expiration.
def _earnings_warning(row):
    if (pd.notna(row['earnings_date_sell']) and
            pd.notna(row['expiration_date_sell']) and
            row['earnings_date_sell'] > pd.Timestamp.now()):  # Earnings in der Zukunft

        days_before_expiration = (row['expiration_date_sell'] - row['earnings_date_sell']).days

        # Warnung nur wenn Earnings VOR Expiration und innerhalb 7 Tage
        if 0 <= days_before_expiration <= 7:
            return f'⚠️ {days_before_expiration} days'

    return ''

if __name__ == "__main__":
    """
     Keep the main for testing purposes
     """

    import time
    import logging
    from src.logger_config import setup_logging
    from src.database import select_into_dataframe

    # enable logging
    setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info(f"Start {__name__} ({__file__})")

    expiration_date = '2025-10-24'
    delta_target = 0.2
    spread_width = 5

    sql_query = """
    SELECT
        symbol,
        expiration_date,
        "option-type",
        strike,
        ask,
        bid,
        delta,
        iv,
        theta,
        close,
        earnings_date,
        days_to_expiration,
        days_to_ernings,
        days_to_expiration - days_to_ernings AS delta_expiration_date_to_earnings_date
    FROM
        OptionDataMerged
    WHERE
        expiration_date =:expiration_date;
    """

    start = time.time()
    df = select_into_dataframe(query=sql_query, params={"expiration_date": expiration_date})
    spreads_df = calc_spreads(df, delta_target, spread_width)
    ende = time.time()

    print(spreads_df.head())
    print(spreads_df.shape)
    print(f"Runtime: {ende - start:.6f} seconds")