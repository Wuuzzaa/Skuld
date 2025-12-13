from massive import RESTClient
from config import MASSIVE_API_KEY, SYMBOLS
import pandas as pd
import time

import asyncio
import aiohttp


async def get_all_option_chains_for_ticker(ticker, session, limit=250):
    """Holt ALLE Options-Chains für einen Ticker mit Pagination"""
    all_results = []
    url = f"https://api.massive.com/v3/snapshot/options/{ticker}"
    params = {
        "limit": limit,
        "apiKey": MASSIVE_API_KEY}

    try:
        page = 1
        while url:
            async with session.get(url, params=params) as response:
                data = await response.json()

                # DEBUG: Komplette Response ausgeben
                if data.get('status') != 'OK':
                    print(f"✗ {ticker} Seite {page}: Status = {data.get('status')}")
                    print(f"  Response: {data}")
                    break

                results = data.get('results', [])
                all_results.extend(results)

                # Nächste Seite URL
                next_url = data.get('next_url')

                if next_url:
                    print(f"  → {ticker}: Seite {page}, {len(all_results)} Optionen")
                    print(f"  → next_url: {next_url}")

                    # WICHTIG: next_url bereits vollständig, aber API-Key könnte fehlen
                    url = next_url
                    # Für next_url: nur API-Key als Parameter
                    params = {
                        "apiKey": MASSIVE_API_KEY}
                    page += 1
                else:
                    url = None

        print(f"✓ {ticker}: {len(all_results)} Optionen gesamt")
        return all_results

    except Exception as e:
        print(f"✗ {ticker}: Exception - {e}")
        import traceback
        traceback.print_exc()
        return []


async def get_option_chains_tickers_async(tickers, limit=250):
    """Holt ALLE Options-Chains für alle Tickers parallel"""
    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [
            get_all_option_chains_for_ticker(ticker, session, limit)
            for ticker in tickers
        ]
        results = await asyncio.gather(*tasks)

    option_chains = []
    for result in results:
        option_chains.extend(result)

    print(f"\n🎉 GESAMT: {len(option_chains)} Optionen von {len(tickers)} Tickers")
    return option_chains

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

    # # Multiple symbols option chains
    # start_time = time.time()
    # get_option_chains_tickers(tickers)
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # Multiple symbols option chains
    start_time = time.time()
    #option_chains = asyncio.run(get_option_chains_tickers_async(tickers, limit=250))
    option_chains = asyncio.run(get_option_chains_tickers_async(SYMBOLS, limit=250))
    print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # # all contracts
    # start_time = time.time()
    # all_contracts()
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")


