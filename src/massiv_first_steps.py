from massive import RESTClient
from config import MASSIVE_API_KEY
import pandas as pd
import time

def get_option_chains_tickers(tickers, limit=250):
    option_chains = []
    for ticker in tickers:
        option_chains.append(get_option_chains(ticker, limit=limit))

def get_option_chains(ticker, limit=250):
    """

    :param ticker: Ticker or symbol of the underlying.
    :param limit: Ratelimit is max 250. The default value.
    :return: Dataframe with all current option chains for the requested ticker.
    """
    client = RESTClient(MASSIVE_API_KEY)

    option_chains = []
    list_snapshot_options_chain = client.list_snapshot_options_chain(
            ticker,
            params={"limit": limit} # 250 max value allowed by the API
    )

    for _ in list_snapshot_options_chain:
        option_chains.append(_)
        print(_.details.ticker)

    print(f"Ticker: {ticker} has {len(option_chains)} option chains")

    return option_chains

def all_contracts():
    client = RESTClient(MASSIVE_API_KEY)

    contracts = []
    underlying_tickers = set()
    for c in client.list_options_contracts(
            order="asc",
            limit=1000,
            sort="ticker",
    ):
        contracts.append(c.ticker)
        underlying_tickers.add(c.underlying_ticker)
        print(c)


    print(f"Amount contracts: {len(contracts)}")
    print(f"Amount symbols{len(underlying_tickers)}")


if __name__ == "__main__":
    ticker = "MSFT"
    tickers = [
        "MSFT",
        "AAPL",
        "AMZN",
        "KO",
        "GOOGL",
        "QQQ",
        "TSLA",
    ]

    # # One symbol option chains
    # start_time = time.time()
    # get_option_chains(ticker)
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # Multiple symbols option chains
    start_time = time.time()
    get_option_chains_tickers(tickers)
    print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # # all contracts
    # start_time = time.time()
    # all_contracts()
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")


