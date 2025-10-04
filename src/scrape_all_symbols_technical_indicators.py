import pandas as pd
import sys
import os
import time
from tradingview_ta import TA_Handler, Interval
from config import PATH_SYMBOLS_EXCHANGE_FILE, PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER, TABLE_TECHNICAL_INDICATORS
from src.database import insert_into_table, truncate_table

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Read symbols and exchanges from Excel
symbols_df = pd.read_excel(PATH_SYMBOLS_EXCHANGE_FILE)
SYMBOLS_EXCHANGE = dict(zip(symbols_df['symbol'], symbols_df['exchange']))
SYMBOLS = list(SYMBOLS_EXCHANGE.keys())

def scrape_and_save_all_symbols_technical_indicators():
    results = []
    for symbol in SYMBOLS:
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
            data = analysis.get_analysis()
            indicators = data.indicators
            indicators["symbol"] = symbol
            indicators["recommendation"] = data.summary.get("RECOMMENDATION")
            indicators["recommendation_buy_amount"] = data.summary.get("BUY")
            indicators["recommendation_neutral_amount"] = data.summary.get("NEUTRAL")
            indicators["recommendation_sell_amount"] = data.summary.get("SELL")
            results.append(indicators)
        except Exception as e:
            print(f"Error with symbol: {symbol}: {e}")
        time.sleep(1)
    df = pd.DataFrame(results)
    df.to_feather(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER)
    truncate_table(TABLE_TECHNICAL_INDICATORS)
    insert_into_table(
        table_name=TABLE_TECHNICAL_INDICATORS,
        dataframe=df,
        if_exists="append"
    )

if __name__ == "__main__":
    scrape_and_save_all_symbols_technical_indicators()
