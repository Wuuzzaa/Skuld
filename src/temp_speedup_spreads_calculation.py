import pandas
import pandas as pd
from config import *


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
        "option"
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

    # Find the best matching option (smallest delta_diff) per symbol
    sell_puts = puts.loc[puts.groupby("symbol")["delta_diff"].idxmin()]
    sell_calls = calls.loc[calls.groupby("symbol")["delta_diff"].idxmin()]

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
        left_on=["symbol", sell_puts["strike"] - spread_width],
        right_on=["symbol", "strike"],
        suffixes=("_sell", "_buy")
    )

    # Merge for calls
    calls = df[df["option-type"] == "call"].copy()

    call_spreads = sell_calls.merge(
        calls,
        how="left",
        left_on=["symbol", sell_calls["strike"] + spread_width],
        right_on=["symbol", "strike"],
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

    del puts, calls, sell_puts, sell_calls

    # spread values calculation
    spreads["spread_width"] = abs(spreads['strike_sell'] - spreads['strike_buy'])
    spreads["max_profit"] = 100 * (spreads["bid_sell"] - spreads["ask_buy"])
    spreads["bpr"] = spreads["spread_width"] * 100 - spreads["max_profit"]
    spreads["profit_to_bpr"] = spreads["max_profit"] / spreads["bpr"]
    spreads["spread_theta"] = spreads["theta_sell"] -spreads["theta_buy"]
    spreads["pop_delta"] = 1 - abs(spreads["delta_sell"])
    spreads["ev_pop_delta"] = (spreads["pop_delta"] * spreads["max_profit"]) - ((1 - spreads["pop_delta"]) * spreads["bpr"])

    return spreads


if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """

    import time

    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    expiration_date = '2025-05-23'
    delta_target = 0.2
    spread_width = 5

    start = time.time()
    spreads_df = get_spreads(df, expiration_date, delta_target, spread_width)
    ende = time.time()

    print(spreads_df.head())
    print(f"Laufzeit: {ende - start:.6f} Sekunden")

    # iterative Lösung: Laufzeit: 53.084366 Sekunden
    pass
