import pandas as pd
import time
from config import *
from yahooquery import Ticker


def get_yahooquery_option_chain():
    tickers = Ticker(SYMBOLS, asynchronous=True)
    df = tickers.option_chain



    # symbol expiration_date and option-type from index to column
    # symbol -> symbol
    # expiration-> expiration_date
    # optionType -> option-type
    df = df.reset_index()

    df = df.rename(columns={
        'symbol': 'symbol',
        'expiration': 'expiration_date',
        'optionType': 'option-type'
    })

    print(df.head())


if __name__ == '__main__':

    start = time.time()
    get_yahooquery_option_chain()
    end = time.time()
    duration = end - start


    print(f"\nDurchlaufzeit: {duration:.4f} Sekunden")
