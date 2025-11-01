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

    # --- Database Persistence ---
    truncate_table(TABLE_ANALYST_PRICE_TARGETS)
    insert_into_table(
        table_name=TABLE_ANALYST_PRICE_TARGETS,
        dataframe=df,
        if_exists="append"
    )