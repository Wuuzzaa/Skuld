import sys
import os
import requests
import pandas as pd
from config import SYMBOLS_EXCHANGE, TABLE_OPTION_DATA_TRADINGVIEW
from src.database import insert_into_table, truncate_table
from src.util import opra_to_osi

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL_OPTION_DATA = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"

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
        
    # --- Database Persistence ---
    truncate_table(TABLE_OPTION_DATA_TRADINGVIEW)
    insert_into_table(
        table_name=TABLE_OPTION_DATA_TRADINGVIEW,
        dataframe=df,
        if_exists="append"
    )