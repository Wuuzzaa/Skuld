import sys
import os

from src.database import insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import get_filtered_symbols_with_logging
import yfinance as yf
import yahooquery as yq
import pandas as pd
import time


def scrape_yahoo_finance_analyst_price_targets():
    print("#" * 80)
    print("Scraping analyst price targets on Yahoo Finance...")
    print("#" * 80)
    
    # https://ranaroussi.github.io/yfinance/reference/yfinance.ticker_tickers.html

    results = []

    # Test mode logic and logging centrally from config
    symbols = get_filtered_symbols_with_logging("Yahoo Finance Analyst Price Targets")

    # Symbole in 500er-Pakete aufteilen
    batch_size = 500
    symbol_batches = [
        " ".join(symbols[i:i + batch_size])
        for i in range(0, len(symbols), batch_size)
    ]

    for symbol_batch in symbol_batches:
        print(f"Scraping batch of {len(symbol_batch)} symbols on Yahoo Finance...")
        tickers = yf.Tickers(symbol_batch)

        for symbol, data in tickers.tickers.items():
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

    # --- Database Persistence ---
    truncate_table(TABLE_ANALYST_PRICE_TARGETS)
    insert_into_table(
        table_name=TABLE_ANALYST_PRICE_TARGETS,
        dataframe=df,
        if_exists="append"
    )

def scrape_yahoo_finance_analyst_price_targets2():
    print("#" * 80)
    print("Scraping analyst price targets on Yahoo Finance...")
    print("#" * 80)
    
    # https://yahooquery.dpguthrie.com/guide/ticker/modules/

    results = []

    # Test mode logic and logging centrally from config
    symbols = get_filtered_symbols_with_logging("Yahoo Finance Analyst Price Targets")

    # Symbole in Pakete aufteilen
    batch_size = 1000
    symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]

    for symbol_batch in symbol_batches:
        tickers = yq.Ticker(symbol_batch)

        print(f"Scraping batch of {len(symbol_batch)} symbols on Yahoo Finance...")
        financial_data = tickers.financial_data

        for symbol, data in financial_data.items():
            # Get mean or set None if the yahoo finance has no data.
            try:
                if "targetMeanPrice" in data:
                    mean_target = data['targetMeanPrice']
                else:
                    print(f"No price target available for {symbol}")
                    mean_target = None
            except Exception as e:
                print(f"Error getting price target for {symbol}: {e} -> {data}")
                mean_target = None

            results.append({"symbol": symbol, "analyst_mean_target": mean_target})

        # 1 request per second api rate limit
        time.sleep(1)

    df = pd.DataFrame(results)
    df.to_feather(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER)

    # --- Database Persistence ---
    truncate_table(TABLE_ANALYST_PRICE_TARGETS)
    insert_into_table(
        table_name=TABLE_ANALYST_PRICE_TARGETS,
        dataframe=df,
        if_exists="append"
    )

def scrape_yahoo_finance_analyst_price_targets3():
    print("#" * 80)
    print("Scraping analyst price targets on Yahoo Finance...")
    print("#" * 80)
    
    # https://yahooquery.dpguthrie.com/guide/ticker/modules/

    results = []

    # Test mode logic and logging centrally from config
    
    print(f"Scraping symbols on Yahoo Finance...")
    yahoo_query = YahooQueryScraper.instance()
    data = yahoo_query.get_modules()

    for symbol, symbol_data in data.items():
        financial_data = symbol_data.get('financialData')
        # Get mean or set None if the yahoo finance has no data.
        try:
            if "targetMeanPrice" in financial_data:
                mean_target = financial_data['targetMeanPrice']
            else:
                print(f"No price target available for {symbol}")
                mean_target = None
        except Exception as e:
            print(f"Error getting price target for {symbol}: {e} -> {financial_data}")
            mean_target = None

        results.append({"symbol": symbol, "analyst_mean_target": mean_target})

    df = pd.DataFrame(results)
    df.to_feather(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER)

    # --- Database Persistence ---
    truncate_table(TABLE_ANALYST_PRICE_TARGETS)
    insert_into_table(
        table_name=TABLE_ANALYST_PRICE_TARGETS,
        dataframe=df,
        if_exists="append"
    )