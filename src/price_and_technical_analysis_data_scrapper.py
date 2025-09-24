import pandas as pd
import sys
import os

from src.database import insert_into_table, truncate_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from tradingview_ta import TA_Handler, Interval, Exchange
from config_utils import get_filtered_symbols_with_logging


def scrape_and_save_price_and_technical_indicators():
    # Get symbols with new configuration system
    symbols = get_filtered_symbols_with_logging("Technical Analysis Scraping")
    
    results = []

    # Use the exchange from SYMBOLS_EXCHANGE mapping (from Excel file)
    for symbol in symbols:
        exchange = SYMBOLS_EXCHANGE.get(symbol)
        if not exchange:
            print(f"WARNING: No exchange found for symbol {symbol}. Skipping.")
            continue
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
            #indicators["exchange"] = exchange
            indicators["recommendation"] = data.summary["RECOMMENDATION"]
            indicators["recommendation_buy_amount"] = data.summary["BUY"]
            indicators["recommendation_neutral_amount"] = data.summary["NEUTRAL"]
            indicators["recommendation_sell_amount"] = data.summary["SELL"]
            # TODO: add price data here

            results.append(indicators)

        except Exception as e:
            print(f"Error with symbol: {symbol}: {e}")  

    # make a dataframe from the results
    df = pd.DataFrame(results)

    df.to_feather(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER)

    # --- Database Persistence ---
    truncate_table(TABLE_TECHNICAL_INDICATORS)
    insert_into_table(
        table_name=TABLE_TECHNICAL_INDICATORS,
        dataframe=df,
        if_exists="append"
    )

