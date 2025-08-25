import pandas as pd
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from tradingview_ta import TA_Handler, Interval, Exchange
from config_utils import validate_config


def scrape_and_save_price_and_technical_indicators():
    # Test mode logic and logging based on config
    active_mode = validate_config()
    if active_mode == "GENERAL_TEST_MODE":
        items = list(SYMBOLS_EXCHANGE.items())[:GENERAL_TEST_MODE_MAX_SYMBOLS]
        print(f"[TESTMODE] Only {GENERAL_TEST_MODE_MAX_SYMBOLS} symbols will be processed.")
    elif active_mode == "MARRIED_PUT_TEST_MODE":
        if MARRIED_PUT_TEST_MODE_MAX_SYMBOLS is not None:
            items = list(SYMBOLS_EXCHANGE.items())[:MARRIED_PUT_TEST_MODE_MAX_SYMBOLS]
            print(f"[MARRIED_PUT_TEST_MODE] Only {MARRIED_PUT_TEST_MODE_MAX_SYMBOLS} symbols will be processed.")
        else:
            items = SYMBOLS_EXCHANGE.items()
            print(f"[MARRIED_PUT_TEST_MODE] All {len(SYMBOLS_EXCHANGE)} symbols will be processed.")
    else:
        items = SYMBOLS_EXCHANGE.items()
        print(f"[PRODUCTION] All {len(SYMBOLS_EXCHANGE)} symbols will be processed.")
    results = []

    for symbol, exchange in items:
        try:
            analysis = TA_Handler(
                symbol=symbol,
                screener="america",
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY
            )

            # get indicator values
            data = analysis.get_analysis()

            # extract values
            indicators = data.indicators
            indicators["symbol"] = symbol
            indicators["recommendation"] = data.summary["RECOMMENDATION"]
            indicators["recommendation_buy_amount"] = data.summary["BUY"]
            indicators["recommendation_neutral_amount"] = data.summary["NEUTRAL"]
            indicators["recommendation_sell_amount"] = data.summary["SELL"]
            # TODO: add price data here

            # add results
            results.append(indicators)

        except Exception as e:
            print(f"Error with symbol: {symbol}: {e}")

    # make a dataframe from the results
    df = pd.DataFrame(results)

    df.to_feather(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER)



