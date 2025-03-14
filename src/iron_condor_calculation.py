import pandas as pd
from config import *
from src.spreads_calculation import get_spreads, calc_JMS


def __create_iron_condor(put_spread, call_spread):
    iron_condor = pd.Series(data={

        # same values for put and call spread
        "symbol": put_spread["symbol"],
        "epiration_date": put_spread["expiration_date"],

        # call spread
        "call_spread_sell_strike": call_spread["sell_strike"],
        "call_spread_sell_price": call_spread["sell_price"],
        "call_spread_sell_delta": call_spread["sell_delta"],
        "call_spread_buy_strike": call_spread["buy_strike"],
        "call_spread_buy_price": call_spread["buy_price"],
        "call_spread_buy_delta": call_spread["buy_delta"],

        # put spread
        "put_spread_sell_strike": put_spread["sell_strike"],
        "put_spread_sell_price": put_spread["sell_price"],
        "put_spread_sell_delta": put_spread["sell_delta"],
        "put_spread_buy_strike": put_spread["buy_strike"],
        "put_spread_buy_price": put_spread["buy_price"],
        "put_spread_buy_delta": put_spread["buy_delta"],

        # iron condor
        "max_profit": call_spread["max_profit"] + put_spread["max_profit"],
        "theta": call_spread["spread_theta"] + put_spread["spread_theta"],
        # max width *100 - total premium for the spreads
        "bpr": max(call_spread["spread_width"], put_spread["spread_width"]) * 100 - (put_spread["max_profit"] + call_spread["max_profit"]),
    })

    # add JMS
    iron_condor["jms"] = calc_JMS(iron_condor, is_iron_condor=True)

    return iron_condor


def get_iron_condors(df, expiration_date, delta_target, spread_width):
    spreads_df = get_spreads(df, expiration_date, delta_target, spread_width)

    iron_condors = []

    for symbol in spreads_df["symbol"].unique():
        # put and call spread for the symbol
        put_spread = spreads_df[(spreads_df["symbol"] == symbol) & (spreads_df["option_type"] == "put")].squeeze()
        call_spread = spreads_df[(spreads_df["symbol"] == symbol) & (spreads_df["option_type"] == "call")].squeeze()

        # make an iron condor out of the two spreads
        iron_condor = __create_iron_condor(put_spread, call_spread)
        iron_condors.append(iron_condor)

    return pd.DataFrame(iron_condors)


if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """

    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    expiration_date = '2025-03-14'
    delta_target = 0.15
    spread_width = 5

    iron_condors_df = get_iron_condors(df, expiration_date, delta_target, spread_width)
    pass