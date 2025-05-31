from yahooquery import Ticker
from datetime import datetime
from config import *
import pandas as pd


def scrape_earning_dates(testmode):
    # check testmode
    if testmode:
        tickers = Ticker(SYMBOLS[:5], asynchronous=True)
    else:
        tickers = Ticker(SYMBOLS, asynchronous=True)

    earnings_dates = {}

    for symbol, data in tickers.calendar_events.items():
        try:
            raw_date = data['earnings']['earningsDate'][0][:10]  # z.B. '2025-07-30'
            date_obj = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
            earnings_dates[symbol] = formatted_date
        except (TypeError, IndexError) as e:
            earnings_dates[symbol] = "No date or no stock"

    # store dataframe
    df = pd.DataFrame(list(earnings_dates.items()), columns=['symbol', 'earnings_date'])
    df.to_feather(PATH_DATAFRAME_EARNING_DATES_FEATHER)


if __name__ == '__main__':
    import time

    start = time.time()
    scrape_earning_dates()
    end = time.time()

    duration = end - start

    print(f"\nDurchlaufzeit: {duration:.4f} Sekunden")

    # Durchlaufzeit: 8.5962 Sekunden Async
    # Durchlaufzeit: 61.5521 Sekunden Sync