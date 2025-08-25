import pandas as pd
import time
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import validate_config
from yahooquery import Ticker


def get_yahooquery_option_chain():
    # Testmode-Logik und Logging zentral aus der Config
    active_mode = validate_config()
    if active_mode == "GENERAL_TEST_MODE":
        symbols = SYMBOLS[:GENERAL_TEST_MODE_MAX_SYMBOLS]
        print(f"[TESTMODE] Only {GENERAL_TEST_MODE_MAX_SYMBOLS} symbols will be processed.")
    elif active_mode == "MARRIED_PUT_TEST_MODE":
        if MARRIED_PUT_TEST_MODE_MAX_SYMBOLS is not None:
            symbols = SYMBOLS[:MARRIED_PUT_TEST_MODE_MAX_SYMBOLS]
            print(f"[MARRIED_PUT_TEST_MODE] Only {MARRIED_PUT_TEST_MODE_MAX_SYMBOLS} symbols will be processed.")
        else:
            symbols = SYMBOLS
            print(f"[MARRIED_PUT_TEST_MODE] All {len(SYMBOLS)} symbols will be processed.")
    else:
        symbols = SYMBOLS
        print(f"[PRODUCTION] All {len(SYMBOLS)} symbols will be processed.")

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
