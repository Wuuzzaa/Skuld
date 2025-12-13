from massive import RESTClient
from config import MASSIVE_API_KEY, SYMBOLS
import pandas as pd
import time

import asyncio
import aiohttp


async def get_tickers_by_market(market, session):
    """Holt alle Tickers für einen bestimmten Market (stocks oder indices)"""
    url = "https://api.massive.com/v3/reference/tickers"
    params = {
        "market": market,
        "active": "true",
        "order": "asc",
        "limit": 1000,
        "sort": "ticker",
        "apiKey": MASSIVE_API_KEY
    }

    tickers = []
    page = 1

    while url:
        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get('status') != 'OK':
                print(f"✗ {market.upper()} Seite {page}: Status = {data.get('status')}")
                break

            results = data.get('results', [])

            for ticker_data in results:
                ticker = ticker_data.get('ticker')
                if ticker:
                    tickers.append(ticker)

            print(f"→ {market.upper()} Seite {page}: +{len(results)} | Gesamt: {len(tickers)}")

            next_url = data.get('next_url')
            if next_url:
                url = next_url
                params = {
                    "apiKey": MASSIVE_API_KEY}
                page += 1
            else:
                url = None

    print(f"✓ {market.upper()}: {len(tickers)} Tickers")
    return tickers


async def get_all_stocks_and_indices():
    """Holt ALLE Stocks UND Indices parallel"""
    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Beide Markets parallel abfragen
        stocks_task = get_tickers_by_market("stocks", session)
        indices_task = get_tickers_by_market("indices", session)

        stocks, indices = await asyncio.gather(stocks_task, indices_task)

    # Kombinieren
    all_tickers = stocks + indices

    print(f"\n🎉 GESAMT: {len(all_tickers)} Tickers")
    print(f"   → Stocks: {len(stocks)}")
    print(f"   → Indices: {len(indices)}")

    return {
        "all": all_tickers,
        "stocks": stocks,
        "indices": indices
    }


async def get_all_option_contracts():
    """Holt ALLE Options-Contracts mit Pagination"""
    url = "https://api.massive.com/v3/reference/options/contracts"
    params = {
        "limit": 1000,  # Max 1000 pro Request
        "apiKey": MASSIVE_API_KEY
    }

    all_contracts = []
    page = 1

    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=1800)  # 30 Min Timeout für viele Seiten

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        while url:
            async with session.get(url, params=params) as response:
                data = await response.json()

                # Status prüfen
                if data.get('status') != 'OK':
                    print(f"✗ Seite {page}: Status = {data.get('status')}")
                    if 'message' in data:
                        print(f"  Message: {data['message']}")
                    break

                results = data.get('results', [])
                all_contracts.extend(results)

                print(f"→ Seite {page}: +{len(results)} Contracts | Gesamt: {len(all_contracts)}")

                # Nächste Seite
                next_url = data.get('next_url')
                if next_url:
                    url = next_url
                    params = {
                        "apiKey": MASSIVE_API_KEY}
                    page += 1
                else:
                    url = None

    print(f"\n✓ ALLE CONTRACTS GELADEN: {len(all_contracts)} Contracts")

    # Unique Underlying Tickers extrahieren
    underlying_tickers = set()
    for contract in all_contracts:
        if contract.get('underlying_ticker'):
            underlying_tickers.add(contract['underlying_ticker'])

    print(f"✓ Unique Symbole: {len(underlying_tickers)}")

    return all_contracts


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


async def get_active_tickers_with_options_fast():
    """Schnellere Version: Nutzt type=CS (Common Stock) und prüft dann Optionen"""

    # Hole alle aktiven Stocks und Indices
    async def get_active_by_market(market, session):
        url = "https://api.massive.com/v3/reference/tickers"
        params = {
            "market": market,
            "active": "true",
            "limit": 1000,
            "apiKey": MASSIVE_API_KEY
        }

        tickers = []
        while url:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if data.get('status') != 'OK':
                    break

                for item in data.get('results', []):
                    if item.get('ticker'):
                        tickers.append(item['ticker'])

                url = data.get('next_url')
                if url:
                    params = {
                        "apiKey": MASSIVE_API_KEY}

        print(f"✓ {market}: {len(tickers)} aktive Tickers")
        return tickers

    # Prüfe ob Ticker Optionen hat
    async def has_options(ticker, session):
        url = f"https://api.massive.com/v3/snapshot/options/{ticker}"
        params = {
            "limit": 1,
            "apiKey": MASSIVE_API_KEY}

        try:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    return ticker
        except:
            pass
        return None

    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=1800)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Hole Stocks und Indices parallel
        stocks, indices = await asyncio.gather(
            get_active_by_market("stocks", session),
            get_active_by_market("indices", session)
        )

        all_tickers = stocks + indices
        print(f"\n📊 Prüfe {len(all_tickers)} Tickers auf Optionen...")

        # Prüfe parallel ob sie Optionen haben (in Batches)
        batch_size = 50
        tickers_with_options = []

        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i + batch_size]
            tasks = [has_options(ticker, session) for ticker in batch]
            results = await asyncio.gather(*tasks)

            batch_with_options = [r for r in results if r is not None]
            tickers_with_options.extend(batch_with_options)

            print(
                f"→ Batch {i // batch_size + 1}: {len(batch_with_options)}/{len(batch)} haben Optionen | Gesamt: {len(tickers_with_options)}")

    print(f"\n🎉 ERGEBNIS: {len(tickers_with_options)} aktive Tickers mit Optionen")
    return sorted(tickers_with_options)


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

    # # Multiple symbols option chains
    # start_time = time.time()
    # #option_chains = asyncio.run(get_option_chains_tickers_async(tickers, limit=250))
    # option_chains = asyncio.run(get_option_chains_tickers_async(SYMBOLS, limit=250))
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # # All symbols option chains
    # start_time = time.time()
    # option_chains = asyncio.run(get_all_option_contracts())
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # # All symbols (stock and indices)
    # start_time = time.time()
    # result = asyncio.run(get_all_stocks_and_indices())
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # All symbols with options (stock and indices)
    start_time = time.time()
    result = asyncio.run(get_active_tickers_with_options_fast())
    print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

    # # all contracts
    # start_time = time.time()
    # all_contracts()
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")


