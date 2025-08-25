import pandas as pd
import time
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import *
from config_utils import validate_config, get_filtered_symbols_with_logging
from yahooquery import Ticker


def get_yahooquery_financials():
    # Use centralized config validation instead of testmode parameter
    symbols_to_use, active_mode = get_filtered_symbols_with_logging("Yahoo Financials")
    
    tickers = Ticker(symbols_to_use, asynchronous=True)

    # request data
    df = tickers.all_financial_data()

    # symbol as column not index
    df.reset_index(inplace=True)

    # ensure asOfDate is a datetime type
    df['asOfDate'] = pd.to_datetime(df['asOfDate'])

    # find index of the most recent row per symbol
    idx = df.groupby('symbol')['asOfDate'].idxmax()

    # create filtered DataFrame
    df = df.loc[idx].reset_index(drop=True)

    # store dataframe
    df.to_feather(PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER)
    df.to_csv('yahooquery_financial.csv', sep=';', decimal=',', index=False)
    pass

if __name__ == '__main__':

    start = time.time()
    get_yahooquery_financials()
    end = time.time()
    duration = end - start

    print(f"\nRuntime: {duration:.4f} seconds")
