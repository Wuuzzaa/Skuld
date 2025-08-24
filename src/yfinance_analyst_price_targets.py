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

    # Testmode-Logik und Logging zentral aus der Config
    active_mode = validate_config()
    if active_mode == "GENERAL_TEST_MODE":
        symbols = SYMBOLS[:GENERAL_TEST_MODE_MAX_SYMBOLS]
        print(f"[TESTMODE] Es werden nur {GENERAL_TEST_MODE_MAX_SYMBOLS} Symbole verarbeitet.")
    else:
        symbols = SYMBOLS
        print(f"[PRODUKTIV] Es werden alle {len(SYMBOLS)} Symbole verarbeitet.")

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
        # time.sleep(1)

    df = pd.DataFrame(results)
    df.to_feather(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER)

