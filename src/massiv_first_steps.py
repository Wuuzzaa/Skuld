import pickle

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


async def get_all_symbols_with_options():
    """Holt ALLE Options-Contracts mit Pagination. Keine Preise keine Griechen"""
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

    df = pd.DataFrame(underlying_tickers)
    df.to_feather("option_symbols.feather")

    return underlying_tickers


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
    """Holt ALLE Options-Chains für alle Tickers parallel. Inkl. Griechen und Preise sowie IV"""
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

def write_pickle(data, filename):
    with open(filename, 'wb') as f:
        pickle.dump(data, file=f)

def load_pickle(filename):
    with open(filename, 'rb') as f:
        return pickle.load(f)

def option_chains_to_dataframe(option_chains):
    """
    Flatten a list of nested dictionaries (option_chains) into a Pandas DataFrame.
    Each key in the top-level dictionary is used as a prefix for its nested keys.

    Args:
        option_chains (list of dict): List of nested dictionaries containing option data.

    Returns:
        pd.DataFrame: Flattened DataFrame with each row representing an option chain entry.
    """
    #todo last updated menschenlesbar
    #todo noch nicht alles flach mit drin. bzw. keys überschneiden sich noch. prefix nutzen.
    #todo close entpricht dem last price

    flattened_data = []

    for entry in option_chains:
        flat_entry = {}
        for top_key, nested_dict in entry.items():
            if isinstance(nested_dict, dict):
                for nested_key, value in nested_dict.items():
                    flat_entry[f"{top_key}.{nested_key}"] = value
            else:
                flat_entry[top_key] = nested_dict
        flattened_data.append(flat_entry)

    df = pd.DataFrame(flattened_data)

    df["day.last_updated_humanreadable"] = (
        pd.to_datetime(df["day.last_updated"], unit='ns', utc=True)
        .dt.tz_convert('Europe/Berlin')
        .dt.strftime('%Y-%m-%d %H:%M:%S')
    )

    return df



if __name__ == "__main__":
    ticker = "MSFT"
    # tickers = [
    #     "MSFT",
    #     "AAPL",
    #     "AMZN",
    #     "KO",
    #     "GOOGL",
    #     "QQQ",
    #     "TSLA",
    # ]

    # #tickers = sorted(pd.read_feather("option_symbols.feather").iloc[:, 0].tolist())[0:2] # only first symbols DEBUG
    # tickers = sorted(pd.read_feather("option_symbols.feather").iloc[:, 0].tolist())
    #
    # # Multiple symbols option chains
    # start_time = time.time()
    # option_chains = asyncio.run(get_option_chains_tickers_async(tickers, limit=250))
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")
    #
    # # store option chains list of dicts
    # write_pickle(option_chains, "option_chains.pickle")

    #load option chains list of dicts
    option_chains = load_pickle(f"option_chains.pickle")

    df = option_chains_to_dataframe(option_chains)
    pass


    # # All symbols with options (stock and indices)
    # start_time = time.time()
    # result = asyncio.run(get_active_tickers_with_options_fast())
    # print(f"Ausführungszeit: {time.time() - start_time:.2f} Sekunden")

"""
https://massive.com/docs/rest/options/snapshots/option-chain-snapshot 

über den Beispielcode ist es zu langsam. Zwar 250 Einträge gleichzeitig. Geht aber besser bei ca. 1,8 Mio Einträgen.
Dazu erst jedes Optionssymbol speichern.
Dann für jedes Optionssymbol eine Query async ebenfalls mit 250 batch -> viel schneller.

get_option_chains_tickers_async
enthält nur die optionsdaten. 

Stockpreise müssen noch gezogen werden.
https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot

df[     (df['ticker'] == 'KO') &     (df['expiration_date'] == '2026-01-16') &     (df['contract_type'] == 'put') &     (df['strike_price'] == 68)]
df[     (df['ticker'] == 'AMZN') &     (df['expiration_date'] == '2026-01-16') &     (df['contract_type'] == 'put') &     (df['strike_price'] == 222.5)]
df[     (df['ticker'] == 'PLTR') &     (df['expiration_date'] == '2026-01-16') &     (df['contract_type'] == 'put') &     (df['strike_price'] == 172.5)]

df[     (df['ticker'] == 'MSFT') &     (df['expiration_date'] == '2026-01-16') &     (df['contract_type'] == 'put') &     (df['strike_price'] == 470)]
"""

