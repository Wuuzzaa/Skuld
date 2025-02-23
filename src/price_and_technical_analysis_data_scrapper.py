import pandas as pd
from config import *
from tradingview_ta import TA_Handler, Interval, Exchange


def scrape_and_save_price_and_technical_indicators(path_outputfile):
    results = []

    for symbol, exchange in SYMBOLS_EXCHANGE.items():
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
            indicators["recommendation"] = data.summary["RECOMMENDATION"]
            indicators["recommendation_buy_amount"] = data.summary["BUY"]
            indicators["recommendation_neutral_amount"] = data.summary["NEUTRAL"]
            indicators["recommendation_sell_amount"] = data.summary["SELL"]
            #todo add price data here

            # add results
            results.append(indicators)

        except Exception as e:
            print(f"Error with symbl: {symbol}: {e}")

    # make a dataframe from the results
    df = pd.DataFrame(results)

    df.to_feather(path_outputfile)



