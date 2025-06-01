import pandas as pd
import time
from config import *
from yahooquery import Ticker


def get_yahooquery_financials(testmode):
    # check testmode
    if testmode:
        tickers = Ticker(SYMBOLS[:5], asynchronous=True)
    else:
        tickers = Ticker(SYMBOLS, asynchronous=True)

    # request data
    df = tickers.all_financial_data()

    # symbol as column not index
    df.reset_index(inplace=True)

    # sicherstellen, dass asOfDate ein Datetime-Typ ist
    df['asOfDate'] = pd.to_datetime(df['asOfDate'])

    # index der jeweils neuesten Zeile je symbol finden
    idx = df.groupby('symbol')['asOfDate'].idxmax()

    # gefilterten DataFrame erzeugen
    df = df.loc[idx].reset_index(drop=True)

    # store dataframe
    df.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER)
    df.to_csv('yahooquery_financial.csv', sep=';', decimal=',', index=False)
    pass

if __name__ == '__main__':

    start = time.time()
    get_yahooquery_financials(testmode=False)
    end = time.time()
    duration = end - start

    print(f"\nDurchlaufzeit: {duration:.4f} Sekunden")
