import pandas
import pandas as pd
from math import sqrt
from scipy.stats import norm
from datetime import datetime
from config import *


def calculate_pop(underlying_price, strike_price, days_to_expiration, implied_volatility, is_call=True):
    """
    Calculates the Probability of Profit (POP) for an option using the normal distribution.

    Parameters:
    - underlying_price (float): Current price of the underlying asset
    - strike_price (float): Option's strike price
    - days_to_expiration (int): Number of days until expiration
    - implied_volatility (float): Implied volatility (e.g., 0.25 for 25%)
    - is_call (bool): True for call options, False for puts

    Returns:
    - pop (float): Probability (between 0 and 1) that the option will expire in-the-money
    """

    # Convert annual volatility to daily and calculate standard deviation
    time_fraction = sqrt(days_to_expiration / 365)
    std_dev = implied_volatility * underlying_price * time_fraction

    if std_dev == 0:
        return 1.0 if (underlying_price > strike_price if is_call else underlying_price < strike_price) else 0.0

    # Calculate the z-score
    z = (strike_price - underlying_price) / std_dev

    # Calculate POP based on option type
    pop = norm.cdf(z) if is_call else 1 - norm.cdf(z)

    return round(pop, 4)


def __load_df_option_columns_only(df, expiration_date):
    option_columns = [
        "symbol",
        "expiration_date",
        "option-type",
        "strike",
        "ask",
        "bid",
        "delta",
        "gamma",
        "iv",
        "rho",
        "theoPrice",
        "theta",
        "vega",
        "option",
        "close",
        "earnings_date"
    ]

    # filter expiration date and only needed columns for the spreads
    df_filtered = df[df["expiration_date"] == expiration_date]
    df_filtered = df_filtered[option_columns].copy()

    return df_filtered


def get_sell_options_by_delta_target(df, delta_target):
    """
    Find the sell options (put and call) per symbol
    by choosing the option with the closest delta to the delta_target.
    For puts, the delta_target is automatically inverted to match the negative delta values in the data.
    """
    # Split into puts and calls
    puts = df[df["option-type"] == "put"].copy()
    calls = df[df["option-type"] == "call"].copy()

    # Invert delta_target for puts because put deltas are negative in the data
    puts["delta_diff"] = (puts["delta"] - (-delta_target)).abs()
    calls["delta_diff"] = (calls["delta"] - delta_target).abs()

    # DEBUG
    # nan_counts = puts["delta_diff"].isna().groupby(puts["symbol"]).sum()
    # nan_counts = nan_counts[nan_counts > 0]
    #
    # if not nan_counts.empty:
    #     print("Symbole mit NaN in delta_diff:")
    #     print(nan_counts)

    # Find the best matching option (smallest delta_diff) per symbol
    sell_puts = puts.loc[puts.groupby("symbol")["delta_diff"].idxmin().dropna()]
    sell_calls = calls.loc[calls.groupby("symbol")["delta_diff"].idxmin().dropna()]

    return sell_puts, sell_calls


def add_buy_options(df, sell_puts, sell_calls, spread_width):
    """
    Find the long options based on the short options and spread width.

    For puts: strike = sell_strike - spread_width
    For calls: strike = sell_strike + spread_width

    :return: put_spreads, call_spreads both pandas dataframes
    """

    #todo only perfect matching strike +- spread_width is selected.

    # Merge for puts
    puts = df[df["option-type"] == "put"].copy()

    put_spreads = sell_puts.merge(
        puts,
        how="left",
        left_on=["symbol", "close", sell_puts["strike"] - spread_width],
        right_on=["symbol", "close", "strike"],
        suffixes=("_sell", "_buy")
    )

    # Merge for calls
    calls = df[df["option-type"] == "call"].copy()

    call_spreads = sell_calls.merge(
        calls,
        how="left",
        left_on=["symbol", "close", sell_calls["strike"] + spread_width],
        right_on=["symbol", "close", "strike"],
        suffixes=("_sell", "_buy")
    )

    return put_spreads, call_spreads


def get_spreads(df, expiration_date, delta_target, spread_width):
    """
    Workflow:
    - filter expiration date and drop not needed columns
    - select the sell options via delta
    - select the buy options via puts and spread width
    - calculate the spread

    :param df:
    :param expiration_date:
    :param delta_target:
    :param spread_width:
    :return:
    """

    df = __load_df_option_columns_only(df, expiration_date)

    # sell options
    sell_puts, sell_calls = get_sell_options_by_delta_target(df, delta_target)

    # add buy options
    puts, calls = add_buy_options(df, sell_puts, sell_calls, spread_width)

    # merge puts and calls
    assert list(puts.columns) == list(calls.columns), "Columns of puts and calls do not match!"

    spreads = pd.concat([puts, calls], ignore_index=True)

    # clear memory
    del puts, calls, sell_puts, sell_calls

    # spread values calculation
    spreads["earnings_date"] = spreads['earnings_date_sell']
    spreads['option_type'] = spreads['option-type_sell']
    spreads["spread_width"] = abs(spreads['strike_sell'] - spreads['strike_buy'])
    spreads["max_profit"] = 100 * (spreads["bid_sell"] - spreads["ask_buy"])
    spreads["bpr"] = spreads["spread_width"] * 100 - spreads["max_profit"]
    spreads["profit_to_bpr"] = spreads["max_profit"] / spreads["bpr"]
    spreads["spread_theta"] = spreads["theta_sell"] - spreads["theta_buy"]
    spreads["pop_delta"] = 1 - abs(spreads["delta_sell"])
    spreads["ev_pop_delta"] = (spreads["pop_delta"] * spreads["max_profit"]) - ((1 - spreads["pop_delta"]) * spreads["bpr"])

    today = pd.Timestamp(datetime.today().date())

    spreads['pop'] = spreads.apply(lambda row: calculate_pop(
        row['close'],
        row['strike_sell'],
        (row['expiration_date_sell'] - today).days,
        row['iv_sell'],
        row['option-type_sell'].lower() == 'call'  # True wenn Call, sonst False
    ), axis=1)
    spreads["ev_pop"] = (spreads["pop"] * spreads["max_profit"]) - ((1 - spreads["pop"]) * spreads["bpr"])

    # remove not needed columns for streamlit data view
    spreads_columns = [
        'symbol',
        'earnings_date',
        'close',
        'option_type',
        #'strike',
        #'expiration_date_sell',
        #'option-type_sell',
        'strike_sell',
        #'ask_sell',
        'bid_sell',
        'delta_sell',
        #'gamma_sell',
        'iv_sell',
        #'rho_sell',
        #'theoPrice_sell',
        #'theta_sell',
        #'vega_sell',
        #'option_sell',
        #'delta_diff',
        #'expiration_date_buy',
        #'option-type_buy',
        'strike_buy',
        'ask_buy',
        #'bid_buy',
        'delta_buy',
        #'gamma_buy',
        #'iv_buy',
        #'rho_buy',
        #'theoPrice_buy',
        #'theta_buy',
        #'vega_buy',
        #'option_buy',
        #'spread_width',
        'max_profit',
        'bpr',
        'profit_to_bpr',
        'spread_theta',
        'pop_delta',
        'ev_pop_delta',
        'pop',
        'ev_pop',
    ]

    return spreads[spreads_columns]


if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """

    import time

    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    expiration_date = '2025-05-30'
    delta_target = 0.2
    spread_width = 5

    start = time.time()
    spreads_df = get_spreads(df, expiration_date, delta_target, spread_width)
    ende = time.time()

    print(spreads_df.head())
    print(f"Laufzeit: {ende - start:.6f} Sekunden")

    # iterative Lösung: Laufzeit: 53.084366 Sekunden
    pass
