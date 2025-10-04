import re
import sys
import os

from src.database import insert_into_table, truncate_table

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pandas as pd

from src.util import opra_to_osi
from config import *
from config_utils import get_symbols_from_config 

BASE_URL_OPTION_DATA = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"


def _extract_strikeprice_from_option_string(option_string):
    # Use a regular expression to find the pattern with 'C' or 'P' followed by the number at the end
    match = re.search(r'[CP](\d+(\.\d+)?)$', option_string)
    if match:
        return float(match.group(1))
    else:
        return None


def _response_json_to_df(data, symbol, exchange, expiration_date):
    # in the JSON response the symbols are the options and not the stock symbols!
    fields = data["fields"]
    options = data["symbols"]
    time = data["time"]

    rows = []
    for option in options:
        row = dict(zip(fields, option["f"]))
        row["option"] = option["s"]
        row["time"] = time
        row["symbol"] = symbol
        row["strike"] = _extract_strikeprice_from_option_string(row["option"])
        row["exchange"] = exchange
        row["expiration_date"] = expiration_date
        rows.append(row)

    df = pd.DataFrame(rows)
    return df


def _response_to_df(data):
    # in the JSON response the symbols are the options and not the stock symbols!
    fields = data["fields"]
    options = data["symbols"]
    time = data["time"]

    rows = []
    for option in options:
        row = dict(zip(fields, option["f"]))
        row["option"] = option["s"]
        row["time"] = time
        rows.append(row)

    df = pd.DataFrame(rows)
    df["option_osi"] = df["option"].apply(opra_to_osi)
    df = df.rename(columns={"root": "symbol"})
    df = df.rename(columns={"expiration": "expiration_date"})

    return df


def scrape_option_data(symbol, expiration_date, exchange, folderpath):
    # JSON Request data
    request_json = {
        "columns": ["ask", "bid", "delta", "gamma", "iv", "option-type", "rho", "strike", "theoPrice", "theta", "vega"],
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "expiration", "operation": "equal", "right": expiration_date},
            {"left": "root", "operation": "equal", "right": f"{symbol}"}
        ],
        "ignore_unknown_fields": False,
        "sort": {"sortBy": "name", "sortOrder": "asc"},
        "index_filters": [{"name": "underlying_symbol", "values": [f"{exchange}:{symbol}"]}]
    }

    # Header
    headers = {
        "Content-Type": "application/json"
    }

    # POST-Request
    response = requests.post(BASE_URL_OPTION_DATA, json=request_json, headers=headers)

    # Handling the response
    if response.status_code == 200:
        print(f"Request {symbol} @{exchange} for expiration {expiration_date} was successful:")

        if response.json()['totalCount'] > 0:
            df = _response_json_to_df(data=response.json(), symbol=symbol, exchange=exchange, expiration_date=expiration_date)

            # add the OSI-Format for option names to be able to merge it later on.
            df["option_osi"] = df["option"].apply(opra_to_osi)
            df.to_feather(folderpath / f"{symbol}_{expiration_date}.feather")
            df.to_csv(folderpath / f"{symbol}_{expiration_date}.csv")
            
            # --- Database Persistence ---
            insert_into_table(
                table_name=TABLE_OPTION_DATA_TRADINGVIEW,
                dataframe=df,
                if_exists="append"
            )
        else:
            print("No data was found")
    else:
        print(f"Request {symbol} @{exchange} for expiration {expiration_date} has failed:")
        print(f"Error: {response.status_code}")
        print(response.text)

def scrape_option_data_trading_view(symbols):
    print(f"Loading for {len(symbols)} symbols option data from TradingView")
    # Ermittle Exchanges für alle Symbole
    symbol_exchange_pairs = [(symbol, SYMBOLS_EXCHANGE[symbol]) for symbol in symbols]
    # Erstelle die Liste für index_filters
    underlying_symbols = [f"{exchange}:{symbol}" for symbol, exchange in symbol_exchange_pairs]

    all_option_data = []

    # Unterteile underlying_symbols in 500er-Pakete (API Limit unbekannt, 500 sollte aber sicher sein)
    batch_size = 500
    symbol_batches = [underlying_symbols[i:i + batch_size] for i in range(0, len(underlying_symbols), batch_size)]
    for symbol_batch in symbol_batches:
        if len(underlying_symbols) > batch_size:
           print(f"Fetching TradingView option data for batch of {len(symbol_batch)} symbols...")
        
        # Additional fields: https://shner-elmo.github.io/TradingView-Screener/fields/options.html

        # root = symbol
        # expiration = expiration date in YYYYMMDD format
        # JSON Request data
        request_json = {
            "columns": ["root","expiration","exchange","strike","ask", "bid", "delta", "gamma", "iv", "option-type", "rho", "theoPrice", "theta", "vega"],
            "filter": [
                {"left": "type", "operation": "equal", "right": "option"}
            ],
            "ignore_unknown_fields": False,
            "sort": {"sortBy": "name", "sortOrder": "asc"},
            "index_filters": [{"name": "underlying_symbol", "values": symbol_batch}]
        }

        # Header
        headers = {
            "Content-Type": "application/json"
        }

        # POST-Request
        response = requests.post(BASE_URL_OPTION_DATA, json=request_json, headers=headers)

        # Handling the response
        if response.status_code == 200:
            print(f"Request batch of {len(symbol_batch)} symbols was successful:")
            data = response.json()
            if data['totalCount'] > 0:
                df = _response_to_df(data=data)
                all_option_data.append(df)
            else:
                print("No data was found")
        else:
            print(f"Request {symbols} has failed:")
            print(f"Error: {response.status_code}")
            print(response.text)
    
    # Combine all data
    df = pd.concat(all_option_data, ignore_index=True)
    df.to_feather(PATH_DATAFRAME_OPTION_DATA_FEATHER)      
        
    # --- Database Persistence ---
    truncate_table(TABLE_OPTION_DATA_TRADINGVIEW)
    insert_into_table(
        table_name=TABLE_OPTION_DATA_TRADINGVIEW,
        dataframe=df,
        if_exists="append"
    )