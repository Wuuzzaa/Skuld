import pandas as pd
import time
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import validate_config, get_filtered_symbols_with_logging
from yahooquery import Ticker


def get_yahooquery_option_chain():
    # Test mode logic and logging centrally from config
    symbols, active_mode = get_filtered_symbols_with_logging("Yahoo Option Chain")

    tickers = Ticker(symbols, asynchronous=True)

    # request data
    df = tickers.option_chain

    # symbol expiration_date and option-type from index to column
    df = df.reset_index()

    df = df.rename(columns={
        'symbol': 'symbol',
        'expiration': 'expiration_date',
        'optionType': 'option-type',
        'volume': 'option_volume',
        'openInterest': 'option_open_interest',
    })

    df.to_feather(PATH_DATAFRAME_YAHOOQUERY_OPTION_CHAIN_FEATHER)


if __name__ == '__main__':
    start = time.time()
    get_yahooquery_option_chain()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")
