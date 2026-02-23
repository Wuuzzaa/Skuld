import sys
import os
import pandas as pd
from config import TABLE_ANALYST_PRICE_TARGETS
from src.database import get_postgres_engine, insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def scrape_yahoo_finance_analyst_price_targets(symbols):
    # https://yahooquery.dpguthrie.com/guide/ticker/modules/

    print("#" * 80)
    print("Scraping analyst price targets on Yahoo Finance...")
    print(f"Scraping symbols on Yahoo Finance...")
    print("#" * 80)

    yahoo_query = YahooQueryScraper.instance(symbols)
    data = yahoo_query.get_modules(modules='financialData')

    results = []

    for symbol, symbol_data in data.items():
        financial_data = symbol_data.get('financialData',symbol_data)

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
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_ANALYST_PRICE_TARGETS)
        insert_into_table(
            connection,
            table_name=TABLE_ANALYST_PRICE_TARGETS,
            dataframe=df,
            if_exists="append"
        )
# debug
if __name__ == "__main__":
    symbols = ["AAPL", "GOOGL", "AMZN"]
    scraper = YahooQueryScraper.instance(symbols)
