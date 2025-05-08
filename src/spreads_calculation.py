import pandas
import pandas as pd
from config import *


def __load_df_option_columns_only(df):
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

    df = df[option_columns].copy()
    return df


def __filter_df_by_option_type_expiration_date_symbol(df, option_type, expiration_date, symbol):
    df_filtered = df.loc[
        (df["symbol"] == symbol) &
        (df["expiration_date"] == expiration_date) &
        (df["option-type"] == option_type)
        ].copy()

    return df_filtered


def __get_option_by_delta_target(df, option_type, expiration_date, symbol, delta_target):
    # Filter the dataframe
    df_filtered = __filter_df_by_option_type_expiration_date_symbol(df, option_type, expiration_date, symbol)

    # add column with the difference between the selected and actual delta
    df_filtered["delta_diff"] = (df_filtered["delta"] - delta_target).abs()

    # no option data found
    if df_filtered.empty:
        return None

    else:
        option: pandas.Series = df_filtered.loc[df_filtered["delta_diff"].idxmin()]
        return option


def __get_option_by_strike_target(df, option_type, expiration_date, symbol, strike):
    # Filter the dataframe
    df_filtered = __filter_df_by_option_type_expiration_date_symbol(df, option_type, expiration_date, symbol)

    # strike filter
    if option_type == "call":
        option = df_filtered[df_filtered["strike"] >= strike].nsmallest(1, "strike")
    elif option_type == "put":
        option = df_filtered[df_filtered["strike"] <= strike].nlargest(1, "strike")

    # squeeze to get a Series out of the one row Dataframe
    return option.squeeze()


def __calc_strike_buy_option(sell_option, option_type, spread_width):
    if option_type == "call":
        strike = sell_option.strike + spread_width
    elif option_type == "put":
        strike = sell_option.strike - spread_width
    else:
        raise ValueError("Option type must be 'call' or 'put'")
    return strike


def __get_sell_option(df, option_type, expiration_date, symbol, delta_target):
    return __get_option_by_delta_target(df, option_type, expiration_date, symbol, delta_target)


def __get_buy_option(df, option_type, expiration_date, symbol, sell_option, spread_width):
    if sell_option is None:
        return None

    strike = __calc_strike_buy_option(sell_option, option_type, spread_width)
    buy_option = __get_option_by_strike_target(df, option_type, expiration_date, symbol, strike)

    return buy_option


def __check_valid_spread_options(sell_option, buy_option):
    if sell_option is None or buy_option is None:
        raise ValueError("Sell_option or buy_option is None -> No Spread possible")

    if sell_option.symbol != buy_option.symbol:
        raise ValueError("Sell and Buy Symbol must be the same")

    if sell_option.expiration_date != buy_option.expiration_date:
        raise ValueError("Sell and Buy Expiration Date must be the same")

    if sell_option['option-type'] != buy_option['option-type']:
        raise ValueError("Sell and Buy Option Type must be the same")


def __calc_JMS_preparatory_values(spread, is_iron_condor=False):
    prep_values = {}

    prep_values["tp_goal"] = JMS_TP_GOAL
    prep_values["mental_stop"] = JMS_MENTAL_STOP

    # the iron condor win probability is 1 - short call delta - short put delta.
    # Where both deltas are absolute.
    if is_iron_condor:
        prep_values["win_prob"] = 1 - abs(spread['call_spread_sell_delta']) - abs(spread['put_spread_sell_delta'])

    else:
        prep_values["win_prob"] = 1 - abs(spread['sell_delta'])

    prep_values["loss_prob"] = 1 - prep_values["win_prob"]
    prep_values["potential_win"] = spread["max_profit"] * prep_values["tp_goal"]
    prep_values["potential_loss"] = spread["max_profit"] * prep_values["mental_stop"]
    prep_values["win_fraction"] = prep_values["potential_win"] / spread["bpr"]
    prep_values["loss_fraction"] = prep_values["potential_loss"] / spread["bpr"]
    prep_values["expected_win_value"] = prep_values["win_prob"] * prep_values["potential_win"]
    prep_values["expected_loss_value"] = prep_values["potential_loss"] * prep_values["loss_prob"]

    return prep_values


def calc_JMS(spread, is_iron_condor=False):
    """
    Calulates Joachims Milchmädchenrechnungs Score.
    Based on the Delta of the short option a mental stop loss and a take profit goal.
    It's a kind of simple expected Value. Further it is normalized with the BPR.
    :param spread:
    :return:
    """
    prep_values = __calc_JMS_preparatory_values(spread, is_iron_condor)
    win_value = prep_values["expected_win_value"]
    loss_value = prep_values["expected_loss_value"]
    jms = (win_value - loss_value) / spread["bpr"] * 100  # *100 for better readability
    jms = round(jms, 2)

    return jms


def __calc_JMS_kelly_criterion(spread, is_iron_condor=False):
    """
    Calculates the kelly criterion based on the values of the JMS calculations.

    For more details, see https://en.wikipedia.org/wiki/Kelly_criterion
    """
    prep_values = __calc_JMS_preparatory_values(spread, is_iron_condor)
    p = prep_values["win_prob"]
    l = prep_values["loss_fraction"]
    q = prep_values["loss_prob"]
    g = prep_values["win_fraction"]
    jms_kelly = (p / l) - (q / g)
    jms_kelly = round(jms_kelly, 2)

    return jms_kelly


def __create_spread(sell_option, buy_option):
    try:
        __check_valid_spread_options(sell_option, buy_option)
    except ValueError:
        return None

    # calculations (jms and jms kelly under the spread creation)
    spread_width = abs(sell_option.strike - buy_option.strike)
    max_profit = 100 * (sell_option.bid - buy_option.ask)
    bpr = spread_width * 100 - max_profit
    profit_to_risk = max_profit / bpr
    spread_theta = sell_option.theta - buy_option.theta

    data = {
        # Same values sell and buy options
        'symbol': sell_option.symbol,
        'option_type': sell_option['option-type'],
        'expiration_date': sell_option.expiration_date,

        # sell option
        'sell_strike': sell_option.strike,
        'sell_price': sell_option.bid,
        'sell_delta': sell_option.delta,
        'sell_vega': sell_option.vega,
        'sell_theta': sell_option.theta,
        'sell_iv': sell_option.iv,

        # buy option
        'buy_strike': buy_option.strike,
        'buy_price': buy_option.ask,
        'buy_delta': buy_option.delta,
        'buy_vega': buy_option.vega,
        'buy_theta': buy_option.theta,
        'buy_iv': buy_option.iv,

        # calculated values
        'spread_width': spread_width,
        'max_profit': max_profit,
        'bpr': bpr,
        'profit_to_risk': profit_to_risk,
        'spread_theta': spread_theta,
    }

    spread = pd.Series(data)

    # add jms and jms kelly to spread values
    spread['jms'] = calc_JMS(spread, is_iron_condor=False)
    spread['jms_kelly'] = __calc_JMS_kelly_criterion(spread, is_iron_condor=False)

    return spread


def get_spreads(df, expiration_date, delta_target, spread_width):
    df = __load_df_option_columns_only(df)
    spreads = []

    for option_type in ['call', 'put']:
        # the scraped and correct delta for puts is negative
        # the userinput should be positive for puts and calls just for simply use of the app
        if option_type == "put":
            delta_target *= -1

        for symbol in SYMBOLS:
            # get sell and buy options with delta and spread width restrictions
            sell_option = __get_sell_option(df, option_type, expiration_date, symbol, delta_target)
            buy_option = __get_buy_option(df, option_type, expiration_date, symbol, sell_option, spread_width)

            # calculate the spread of both options
            spread = __create_spread(sell_option, buy_option)

            if spread is not None:
                spreads.append(spread)

    spread_df = pd.DataFrame(spreads)

    return spread_df


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

