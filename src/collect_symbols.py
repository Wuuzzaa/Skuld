import io
import time
import pandas as pd
import requests

from config import SYMBOLS

import yfinance as yf

from src.dividend_radar import download_xlsx_file
from src.symbols_exchange import SYMBOLS_EXCHANGE


def get_stock_exchange(symbol):
    stock = yf.Ticker(symbol)
    return stock.info.get('exchange')


def load_dividendradar_symbols():
    content = download_xlsx_file()
    df = pd.read_excel(io.BytesIO(content), sheet_name = "All", header = 2)
    symbols = set(df.Symbol.unique())
    return symbols


def get_most_active_symbols(n_most=250):
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?scrIds=most_actives&count={n_most}&start=0"

    # api request
    response = requests.get(url, headers={
        "User-Agent": "Mozilla/5.0"})

    # JSON extract
    data = response.json()

    # symbol names list
    symbols = [item["symbol"] for item in data["finance"]["result"][0]["quotes"]]
    # exchanges = [item["exchange"] for item in data["finance"]["result"][0]["quotes"]]

    return symbols


def get_symbols_exchange_dict(symbols):
    # remove symbols which are not listed on yahoo finance
    symbols_not_on_yahoo_finance = {"BXS", "SQ"}
    symbols = sorted(list(set(symbols) - symbols_not_on_yahoo_finance))

    # dividenradar uses . yahoo - for b-stocks
    symbols_string = " ".join(symbols)
    symbols_string = symbols_string.replace("ARTN.A", "ARTNA")
    symbols_string = symbols_string.replace("DGIC.A", "DGICA")
    symbols_string = symbols_string.replace("DGIC.B", "DGICB")
    symbols_string = symbols_string.replace("FCNC.A", "FCNCA")
    symbols_string = symbols_string.replace("RBCA.A", "RBCAA")
    symbols_string = symbols_string.replace("RUSH.A", "RUSHA")
    symbols_string = symbols_string.replace(".", "-")

    # request all symbols
    tickers = yf.Tickers(symbols_string)

    symbols_exchange_dict = dict()

    for symbol in tickers.tickers:
        print(symbol)
        exchange = tickers.tickers[symbol].fast_info.exchange
        print(f"{symbol}: {exchange}")
        symbols_exchange_dict[symbol] = exchange

    symbols_exchange_dict = yahoo_exchanges_2_tradingview(symbols_exchange_dict)

    return symbols_exchange_dict


def yahoo_exchanges_2_tradingview(symbols_exchange_dict):
    yahoo_2_tradingview_exchange = {
            'NYQ': 'NYSE',
            'NMS': 'NASDAQ',
            'NCM': 'NASDAQ',  # probably wrong NASDAQ Capital Market.
            'NGM': 'NASDAQ',  # probably wrong Nasdaq Global Market
            'ASE': 'AMEX',
            'PCX': 'NYSE'  # probably wrong Pacific Exchange
    }

    new_symbols_exchange_dict = {}

    # map the exchanges
    for symbol, exchange in symbols_exchange_dict.items():
        mapped_exchange = yahoo_2_tradingview_exchange.get(exchange)
        new_symbols_exchange_dict[symbol] = mapped_exchange

    return new_symbols_exchange_dict


# def get_all_exchanges_for_symbols(symbols):
#     """
#     Yahoo Finance API Rate Limits:
#     https://help.yahooinc.com/dsp-api/docs/rate-limits
#
#     :param symbols: list of symbols
#     :return: dict key: symbol, value: exchange
#     """
#     yahoo_2_tradingview_exchange = {
#         'NYQ': 'NYSE',
#         'NMS': 'NASDAQ',
#         'NCM': 'NASDAQ',  # probably wrong NASDAQ Capital Market.
#         'NGM': 'NASDAQ',  # probably wrong Nasdaq Global Market
#         'ASE': 'AMEX',
#         'PCX': 'NYSE'  # probably wrong Pacific Exchange
#     }
#
#     # DEBUG
#     # raw_exchanges = {}
#     #
#     # for symbol in symbols:
#     #     try:
#     #         print(f"request: {symbol}")
#     #         exchange_dict[symbol] = get_stock_exchange(symbol)
#     #     except Exception as e:
#     #         print(f"Fehler bei {symbol}: {e}")
#     #
#     #     time.sleep(1)
#
#     # DEBUG
#     raw_exchanges = SYMBOLS_EXCHANGE
#
#     exchange_dict = {}
#
#     # map the exchanges
#     for symbol, exchange in raw_exchanges.items():
#         mapped_exchange = yahoo_2_tradingview_exchange.get(exchange)
#         exchange_dict[symbol] = mapped_exchange
#
#     return exchange_dict


if __name__ == '__main__':
    """
    PLAN:
    - download dividendradar excel file
    - download tastytrade list
    - merge both
    - get the exchange for each symbol with yf
    - map the exchangenames from yf to tradingview
    - store the symbols and exchange dict to symbols_exchange.py
    - in the config read from this file
    """

    # merge dividend radar with tastytrade list and the most active stocks according to yahoo finance
    tastytrade_symbols = SYMBOLS
    most_active_symbols = get_most_active_symbols()

    # debug daten wieder laden.
    dividendradar_symbols = load_dividendradar_symbols()
    #dividendradar_symbols = SYMBOLS_EXCHANGE.keys()

    print(f"tastytrade_symbols: {len(tastytrade_symbols)}")
    print(f"most_active_symbols: {len(most_active_symbols)}")
    print(f"dividendradar_symbols: {len(dividendradar_symbols)}")

    symbols = sorted(list(set(dividendradar_symbols) | set(tastytrade_symbols) | set(most_active_symbols)))

    print(f"symbols after merge: {len(symbols)}")


    symbols_exchange = get_symbols_exchange_dict(symbols)
    pass






