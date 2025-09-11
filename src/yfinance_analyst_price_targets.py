import sys
import os

from src.database import insert_into_table, truncate_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import get_filtered_symbols_with_logging
import yfinance as yf
import pandas as pd
import time


def scrape_yahoo_finance_analyst_price_targets():
    print("#" * 80)
    print("Scraping analyst price targets on Yahoo Finance...")
    print("#" * 80)

    results = []

    # Test mode logic and logging centrally from config
    symbols = get_filtered_symbols_with_logging("Yahoo Finance Analyst Price Targets")

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

    # --- Database Persistence ---
    truncate_table(TABLE_ANALYST_PRICE_TARGETS)
    insert_into_table(
        table_name=TABLE_ANALYST_PRICE_TARGETS,
        dataframe=df,
        if_exists="append"
    )