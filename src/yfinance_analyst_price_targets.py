from config import *
import yfinance as yf
import pandas as pd
import time


def scrape_yahoo_finance_analyst_price_targets(testmode):
    print("#"*80)
    print(f"Scraping analyst price targets on Yahoo Finance...")
    print("#"*80)

    results = []

    # Yahoo Finance API Rate Limits:
    # https://help.yahooinc.com/dsp-api/docs/rate-limits

    # check Testmode
    if testmode:
        symbols = SYMBOLS[:5]
    else:
        symbols = SYMBOLS

    for symbol in symbols:
        print(f"Scraping {symbol} on Yahoo Finance...")
        data = yf.Ticker(symbol)

        # Get mean or set None if the yahoo finance has no data.
        # Mostly no data for index of resources
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

