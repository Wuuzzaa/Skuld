import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import validate_config
import yfinance as yf
import pandas as pd
import time


def scrape_yahoo_finance_analyst_price_targets():
    print("#" * 80)
    print("Scraping analyst price targets on Yahoo Finance...")
    print("#" * 80)

    results = []

    # Test mode logic and logging centrally from config
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

    for symbol in symbols:
        print(f"Scraping {symbol} on Yahoo Finance...")
        data = yf.Ticker(symbol)

        # Get mean or set None if the yahoo finance has no data.
        try:
            mean_target = data.analyst_price_targets.get("mean", None)
        except Exception as e:
            print(f"Error getting price target for {symbol}: {e}")
            mean_target = None

        results.append({"symbol": symbol, "analyst_mean_target": mean_target})

        # 1 request per second api rate limit
        time.sleep(1)

    df = pd.DataFrame(results)
    df.to_feather(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER)

