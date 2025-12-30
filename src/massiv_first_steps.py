import logging
import pandas as pd
import asyncio
import aiohttp
from typing import Union, List
from massive import RESTClient
from tqdm import tqdm
from config import MASSIVE_API_KEY, SYMBOLS, PATH_LOG_FILE
from src.decorator_log_function import log_function
from src.logger_config import setup_logging

setup_logging(log_file=PATH_LOG_FILE, log_level=logging.DEBUG, console_output=True)
logger = logging.getLogger(__name__)
logger.info("Start Massiv API test")


async def __get_tickers_by_market(market, session):
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

@log_function
async def get_all_stocks_and_indices():
    """Holt ALLE Stocks UND Indices parallel"""
    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Beide Markets parallel abfragen
        stocks_task = __get_tickers_by_market("stocks", session)
        indices_task = __get_tickers_by_market("indices", session)

        stocks, indices = await asyncio.gather(stocks_task, indices_task)

    # Kombinieren
    all_tickers = stocks + indices

    return {
        "all": all_tickers,
        "stocks": stocks,
        "indices": indices
    }

async def __get_all_option_chains_for_ticker(ticker, session, limit=250):
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
                    break

                results = data.get('results', [])
                all_results.extend(results)

                # Nächste Seite URL
                next_url = data.get('next_url')

                if next_url:
                    # WICHTIG: next_url bereits vollständig, aber API-Key könnte fehlen
                    url = next_url
                    # Für next_url: nur API-Key als Parameter
                    params = {
                        "apiKey": MASSIVE_API_KEY}
                    page += 1
                else:
                    url = None

        return all_results

    except Exception as e:
        print(f"✗ {ticker}: Exception - {e}")
        import traceback
        traceback.print_exc()
        return []


async def __get_option_chains_tickers_async(tickers, limit=250):
    """Holt ALLE Options-Chains für alle Tickers parallel. Inkl. Griechen und Preise sowie IV"""
    connector = aiohttp.TCPConnector(limit=0)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [
            __get_all_option_chains_for_ticker(ticker, session, limit)
            for ticker in tickers
        ]
        results = await asyncio.gather(*tasks)

    option_chains = []
    for result in results:
        option_chains.extend(result)

    return option_chains

@log_function
async def get_active_tickers_with_options():
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

        # Prüfe parallel ob sie Optionen haben (in Batches)
        batch_size = 50
        tickers_with_options = []

        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i + batch_size]
            tasks = [has_options(ticker, session) for ticker in batch]
            results = await asyncio.gather(*tasks)

            batch_with_options = [r for r in results if r is not None]
            tickers_with_options.extend(batch_with_options)
    return sorted(tickers_with_options)

@log_function
def __option_chains_to_dataframe(option_chains):
    """
    Flatten a list of nested dictionaries (option_chains) into a Pandas DataFrame using json_normalize.
    Optimized for speed and readability.

    Args:
        option_chains (list of dict): List of nested dictionaries containing option data.

    Returns:
        pd.DataFrame: Flattened DataFrame with human-readable timestamps.
    """
    # todo close entpricht dem last price

    chunks = []
    chunk_size = 1000
    for i in tqdm(range(0, len(option_chains), chunk_size)):
        chunk = option_chains[i:i + chunk_size]
        chunks.append(pd.json_normalize(chunk, sep="."))
    df = pd.concat(chunks, ignore_index=True)

    # Convert timestamps in a vectorized way
    df["day.last_updated_humanreadable"] = (
        pd.to_datetime(df["day.last_updated"], unit='ns', utc=True)
        .dt.tz_convert('Europe/Berlin')
        .dt.strftime('%Y-%m-%d %H:%M:%S')
    )

    return df

@log_function
def get_option_chains_df(tickers: Union[List[str], str] = "auto", limit=250) -> pd.DataFrame:
    """
    Fetches option chains for a list of tickers and returns the data as a pandas DataFrame.

    Parameters:
    -----------
    tickers : Union[List[str], str], optional
        A list of stock tickers (e.g., ["AAPL", "TSLA"]) or the string "auto".
        If "auto" is provided, the function fetches active tickers with options automatically.
        Default is "auto".
    limit : int, optional
        The maximum number of option chains to fetch per ticker. Default is 250.

    Returns:
    --------
    pd.DataFrame
        A DataFrame containing the option chains data for the specified tickers.

    Example:
    --------
    >>> df = get_option_chains_df(tickers=["AAPL", "TSLA"], limit=100)
    >>> print(df.head())
    """
    if tickers == "auto":
        tickers = asyncio.run(get_active_tickers_with_options())
    option_chains = asyncio.run(__get_option_chains_tickers_async(tickers, limit=limit))
    df = __option_chains_to_dataframe(option_chains)
    return df

if __name__ == "__main__":
    all_tickers = asyncio.run(get_all_stocks_and_indices())
    tickers_with_options = asyncio.run(get_active_tickers_with_options())
    df = get_option_chains_df(tickers=tickers_with_options)
    pass


"""
https://massive.com/docs/rest/options/snapshots/option-chain-snapshot 

all_tickers["stocks"] enthält alle aktien -> brauchen wir
tickers_with_options enthält alle ticker(aktien, index, rohstoffe etc.) mit optionen -> brauchen wir
set aus den beiden bilden.


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

