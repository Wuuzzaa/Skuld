import logging
import sys
import os
import pandas as pd
from config import TABLE_STOCK_ASSET_PROFILES_YAHOO
from src.database import get_postgres_engine, insert_into_table, truncate_table
from src.yahooquery_scraper import YahooQueryScraper

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logger = logging.getLogger(__name__)

def load_asset_profile(symbols):
    logger.info("Loading Yahoo Asset Profiles")
    yahoo_query = YahooQueryScraper.instance(symbols)
    data = yahoo_query.get_modules(modules='assetProfile')

    asset_profiles = {}
    for symbol, symbol_data in data.items():
        asset_profile_data = symbol_data.get('assetProfile', symbol_data)
        long_business_summary = asset_profile_data.get('longBusinessSummary')
        industry = asset_profile_data.get('industry')
        sector = asset_profile_data.get('sector')
        country = asset_profile_data.get('country')

        price_data = symbol_data.get('price', {})
        name = price_data.get('shortName')  # Fallback to symbol if name is not available

        asset_profiles[symbol] = {
            'name': name, 
            'long_business_summary': long_business_summary,
            'industry': industry,
            'sector': sector,
            'country': country
        }

    # store dataframe
    df = pd.DataFrame.from_dict(asset_profiles, orient='index').reset_index().rename(columns={'index': 'symbol'})
    if len(df) == 0:
        raise Exception("No Data fetching asset profiles from Yahoo API")
    # --- Database Persistence ---
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_ASSET_PROFILES_YAHOO)
        insert_into_table(
            connection,
            table_name=TABLE_STOCK_ASSET_PROFILES_YAHOO,
            dataframe=df,
            if_exists="append"
        )