import pandas as pd
from config import *
from src.spreads_calculation import calc_spreads


def get_iron_condors(df, expiration_date, delta_target, spread_width):
    spreads_df = calc_spreads(df, expiration_date, delta_target, spread_width)

    # separate call and put spreads in own dataframes
    puts = spreads_df[spreads_df['option_type'] == 'put'].copy()
    calls = spreads_df[spreads_df['option_type'] == 'call'].copy()

    # set the same index on both based on the symbol.
    # Each df has exactly one line of each symbol, so it matches.
    puts.set_index('symbol', inplace=True)
    calls.set_index('symbol', inplace=True)

    # rename columns for Merge
    puts = puts.rename(columns=lambda x: f"put_{x}" if x != "symbol" else x)
    calls = calls.rename(columns=lambda x: f"call_{x}" if x != "symbol" else x)

    # merge via symbol
    iron_condors = pd.merge(puts, calls, on="symbol", how="inner")

    # calculate iron condor values
    iron_condors['max_profit'] = iron_condors['call_max_profit'] + iron_condors['put_max_profit']
    iron_condors['theta'] = iron_condors['call_spread_theta'] + iron_condors['put_spread_theta']
    iron_condors['bpr'] = spread_width * 100 - iron_condors['max_profit']
    iron_condors['pop'] = iron_condors['call_pop'] * iron_condors['put_pop']
    iron_condors['ev_pop'] = (iron_condors['max_profit'] * iron_condors['pop']) - ((1-iron_condors['pop']) * iron_condors['bpr'])
    iron_condors['close'] = iron_condors['put_close']  # put and call close are the same
    iron_condors['profit_to_bpr'] = iron_condors['max_profit'] / iron_condors['bpr']

    # get symbol as column again and numeric index of the df
    iron_condors.reset_index(inplace=True)

    # select which columns should be returned to streamlit view
    streamlit_columns = [
        'symbol',
        'close',
        'max_profit',
        'profit_to_bpr',
        'theta',
        'bpr',
        'pop',
        'ev_pop',

        # 'put_close',
        # 'put_option_type',
        'put_strike_sell',
        # 'put_bid_sell',
        # 'put_delta_sell',
        # 'put_iv_sell',
        'put_strike_buy',
        # 'put_ask_buy',
        # 'put_delta_buy',
        # 'put_max_profit',
        # 'put_bpr',
        # 'put_profit_to_bpr',
        # 'put_spread_theta',
        # 'put_pop_delta',
        # 'put_ev_pop_delta',
        # 'put_pop',
        # 'put_ev_pop',
        # 'call_close',
        # 'call_option_type',
        'call_strike_sell',
        # 'call_bid_sell',
        # 'call_delta_sell',
        # 'call_iv_sell',
        'call_strike_buy',
        # 'call_ask_buy',
        # 'call_delta_buy',
        # 'call_max_profit',
        # 'call_bpr',
        # 'call_profit_to_bpr',
        # 'call_spread_theta',
        # 'call_pop_delta',
        # 'call_ev_pop_delta',
        # 'call_pop',
        # 'call_ev_pop',
    ]

    return iron_condors[streamlit_columns]


if __name__ == "__main__":
    """
    Keep the main for testing purposes
    """

    import time

    # df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    expiration_date = '2025-05-23'
    delta_target = 0.2
    spread_width = 5

    start = time.time()
    iron_condors = get_iron_condors(df, expiration_date, delta_target, spread_width)
    ende = time.time()

    print(iron_condors.head())
    print(f"Runtime: {ende - start:.6f} seconds")