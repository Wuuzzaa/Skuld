import pandas as pd
import sys
import os

from src.database import insert_into_table, truncate_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from tradingview_ta import TA_Handler, Interval, Exchange, get_multiple_analysis
from config_utils import get_filtered_symbols_with_logging


def scrape_and_save_price_and_technical_indicators():
    # Get symbols with new configuration system
    symbols = get_filtered_symbols_with_logging("Technical Analysis Scraping")
    # Ermittle Exchanges für alle Symbole
    symbol_exchange_pairs = [(symbol, SYMBOLS_EXCHANGE[symbol]) for symbol in symbols]
    # Erstelle die Liste für index_filters
    underlying_symbols = [f"{exchange}:{symbol}" for symbol, exchange in symbol_exchange_pairs]


    results = []
    analysis = {}  # als Dictionary initialisieren

    # Unterteile underlying_symbols in 500er-Pakete (API Limit)
    batch_size = 500
    symbol_batches = [underlying_symbols[i:i + batch_size] for i in range(0, len(underlying_symbols), batch_size)]
    for symbol_batch in symbol_batches:
        analysis_symbol_batch = get_multiple_analysis(screener="america", interval=Interval.INTERVAL_1_HOUR, symbols=symbol_batch)
        analysis.update(analysis_symbol_batch)  # analysis_symbol_batch muss ein dict sein

    # Use the exchange from SYMBOLS_EXCHANGE mapping (from Excel file)
    for symbol_ in analysis:
        exchange = symbol_.split(":")[0]
        symbol = symbol_.split(":")[1]
        if not exchange:
            print(f"WARNING: No exchange found for symbol {symbol}. Skipping.")
            continue
        try:
            # get indicator values
            data = analysis[symbol_]

            # extract values
            indicators = data.indicators
            indicators["symbol"] = symbol
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

    # --- Database Persistence ---
    truncate_table(TABLE_TECHNICAL_INDICATORS)
    insert_into_table(
        table_name=TABLE_TECHNICAL_INDICATORS,
        dataframe=df,
        if_exists="append"
    )

