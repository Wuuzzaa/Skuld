from config import *
import yfinance as yf
import pandas as pd


def scrape_yahoo_finance_analyst_price_targets(symbols):
    print("#"*80)
    print(f"Scraping analyst price targets on Yahoo Finance...")
    print("#"*80)

    results = []

    for symbol in symbols:
        print(f"Scraping {symbol} on Yahoo Finance...")
        data = yf.Ticker(symbol)

        # Get mean or set None if the yahoo finance have no data. mostly no data for index of ressources
        mean_target = data.analyst_price_targets.get("mean", None)

        results.append({"symbol": symbol, "analyst_mean_target": mean_target})

    df = pd.DataFrame(results)
    df.to_csv(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_CSV, index=False)

