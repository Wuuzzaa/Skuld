import re
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import pandas as pd

from src.util import opra_to_osi
from config_utils import validate_config 

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
        else:
            print("No data was found")
    else:
        print(f"Request {symbol} @{exchange} for expiration {expiration_date} has failed:")
        print(f"Error: {response.status_code}")
        print(response.text)

