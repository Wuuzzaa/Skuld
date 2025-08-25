import io
import pandas as pd
import requests
import re
import yfinance as yf
from config import PATH_SYMBOLS_EXCHANGE_FILE
from src.dividend_radar import download_xlsx_file


def get_tastytrade_symbols():
    URL_TASTY_TRADE_LIST = "https://finance.yahoo.com/quotes/AA,AAL,AAPL,AES,AMD,AMZN,AVGO,BA,BABA,BIDU,BYND,C,CAT,COF,COST,CRM,CRON,CRWD,CSCO,DIA,DIS,EEM,EWZ,FL,FXI,GDX,GDXJ,GE,GILD,GLD,GM,GOOG,GS,HAL,HD,HPE,IBM,IWM,JPM,LOW,M,MCD,META,MMM,MRVL,MSFT,MU,NFLX,NIO,NVDA,ORCL,PG,QCOM,QQQ,ROKU,SBUX,SHOP,SLV,SMH,SNAP,SPY,TGT,TLT,TSLA,UBER,USO,V,WBA,WFC,WMT,X,XBI,XLU,XOM,JD,XOP/"

    match = re.search(r"quotes/([^/]+)", URL_TASTY_TRADE_LIST)
    if match:
        tastytradesymbols = match.group(1).split(',')

    return tastytradesymbols


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

    return symbols


def get_symbols_exchange_dict(symbols):
    # remove symbols which are not listed on yahoo finance
    symbols_not_on_yahoo_finance = {"BXS", "SQ"}
    symbols = sorted(list(set(symbols) - symbols_not_on_yahoo_finance))

    symbols_string = " ".join(symbols)

    # neeed some adjustments dividenradar uses . yahoo - for b-stocks???
    # symbols_string = symbols_string.replace("ARTN.A", "ARTNA")
    # symbols_string = symbols_string.replace("DGIC.A", "DGICA")
    # symbols_string = symbols_string.replace("DGIC.B", "DGICB")
    # symbols_string = symbols_string.replace("FCNC.A", "FCNCA")
    # symbols_string = symbols_string.replace("RBCA.A", "RBCAA")
    # symbols_string = symbols_string.replace("RUSH.A", "RUSHA")
    # symbols_string = symbols_string.replace(".", "-")

    # request all symbols
    tickers = yf.Tickers(symbols_string)

    symbols_exchange_dict = dict()

    for symbol in tickers.tickers:
        try:
            exchange = tickers.tickers[symbol].fast_info.exchange
            print(f"{symbol}: {exchange}")
            symbols_exchange_dict[symbol] = exchange
        except KeyError as e:
            error = f"Exception with symbol: {symbol}: {e}"
            print(error)

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


if __name__ == '__main__':
    #     """
    #     Yahoo Finance API Rate Limits:
    #     https://help.yahooinc.com/dsp-api/docs/rate-limits

    # merge dividend radar with tastytrade list and the most active stocks according to yahoo finance
    tastytrade_symbols = get_tastytrade_symbols()
    most_active_symbols = get_most_active_symbols()
    dividendradar_symbols = load_dividendradar_symbols()

    print(f"tastytrade_symbols: {len(tastytrade_symbols)}")
    print(f"most_active_symbols: {len(most_active_symbols)}")
    print(f"dividendradar_symbols: {len(dividendradar_symbols)}")

    symbols = sorted(list(set(dividendradar_symbols) | set(tastytrade_symbols) | set(most_active_symbols)))

    # remove symbols with '.'
    # todo make this run with symbols containing a "."
    symbols = [s for s in symbols if '.' not in s]

    print(f"symbols after merge (without '.' in symbolname): {len(symbols)}")

    symbols_exchange = get_symbols_exchange_dict(symbols)

    # store the symbol exchange data
    df = pd.DataFrame(list(symbols_exchange.items()), columns=['symbol', 'exchange'])
    df.to_excel(PATH_SYMBOLS_EXCHANGE_FILE, index=False)
