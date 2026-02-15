from src.database import insert_into_table, insert_into_table_bulk, select_into_dataframe
import logging
import pandas as pd
import asyncio
import aiohttp
from typing import Union, List
from tqdm import tqdm
from config import MASSIVE_API_KEY, TABLE_OPTION_DATA_MASSIVE, TABLE_STOCK_SYMBOLS_MASSIVE
from src.database import get_postgres_engine, truncate_table
from src.decorator_log_function import log_function
from src.logger_config import setup_logging
from src.stock_volatility import calculate_and_store_stock_implied_volatility
from src.util import executed_as_github_action

logger = logging.getLogger(__name__)

# DEBUG FUNKTION
async def __get_tickers_by_market_ticker_root_test(market, session):
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
    tickers_root = []
    page = 1

    while url:
        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get('status') != 'OK':
                break

            results = data.get('results', [])

            for ticker_data in results:
                ticker = ticker_data.get('ticker')
                ticker_root = ticker_data.get('ticker_root')

                if ticker:
                    tickers.append(ticker)
                    tickers_root.append(ticker_root)

            next_url = data.get('next_url')
            if next_url:
                url = next_url
                params = {
                    "apiKey": MASSIVE_API_KEY}
                page += 1
            else:
                url = None

    return tickers

async def __get_tickers_by_market(market, session):
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
                break

            results = data.get('results', [])

            for ticker_data in results:
                ticker = ticker_data.get('ticker')
                if ticker:
                    tickers.append(ticker)

            next_url = data.get('next_url')
            if next_url:
                url = next_url
                params = {
                    "apiKey": MASSIVE_API_KEY}
                page += 1
            else:
                url = None

    return tickers

async def __get_tickers_with_exchange_by_market(session):
    url = "https://api.massive.com/v3/reference/tickers"
    params = {
        "market": "stocks",
        "active": "true",
        "order": "asc",
        "limit": 1000,
        "sort": "ticker",
        "apiKey": MASSIVE_API_KEY
    }

    tickers = {}
    page = 1

    while url:
        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get('status') != 'OK':
                break

            results = data.get('results', [])

            for ticker_data in results:
                ticker = ticker_data.get('ticker')
                primary_exchange = ticker_data.get('primary_exchange')
                if ticker:
                    tickers[ticker] = primary_exchange

            next_url = data.get('next_url')
            if next_url:
                url = next_url
                params = {
                    "apiKey": MASSIVE_API_KEY}
                page += 1
            else:
                url = None

    return tickers

@log_function
async def get_all_stocks_and_indices():
    connector = aiohttp.TCPConnector(limit=20)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Beide Markets parallel abfragen
        stocks_task = __get_tickers_by_market("stocks", session)
        indices_task = __get_tickers_by_market("indices", session)
        stocks_with_exchange_task = __get_tickers_with_exchange_by_market(session)

        stocks, indices, stocks_with_exchange = await asyncio.gather(stocks_task, indices_task, stocks_with_exchange_task)

        # DEBUG
        # test = __get_tickers_by_market_ticker_root_test("stocks", session)
        # stocks = await asyncio.gather(test)

    # DEBUG
    #return stocks

    all_tickers = stocks + indices

    return {
        "all": all_tickers,
        "stocks": stocks,
        "indices": indices,
        "stocks_with_exchange": stocks_with_exchange
    }

async def __get_all_option_chains_for_ticker(ticker, session, limit=250):
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
                    logger.error(f"{ticker}: Error fetching option chains - {data.get('error')}")
                    raise Exception(f"Error fetching option chains - {data.get('error')}")
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
    connector = aiohttp.TCPConnector(limit=20)
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

    if len(option_chains) == 0:
        logger.error("No option chains data found for any tickers")
        raise Exception("No option chains data found for any tickers")
    
    return option_chains

@log_function
async def get_active_tickers_with_options():
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

    connector = aiohttp.TCPConnector(limit=20)
    timeout = aiohttp.ClientTimeout(total=1800)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Hole Stocks und Indices parallel
        stocks, indices = await asyncio.gather(
            get_active_by_market("stocks", session),
            get_active_by_market("indices", session)
        )

        all_tickers = stocks + indices

        # Prüfe parallel ob sie Optionen haben (in Batches)
        batch_size = 20
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
    chunks = []
    chunk_size = 1000
    for i in tqdm(range(0, len(option_chains), chunk_size)):
        chunk = option_chains[i:i + chunk_size]
        chunks.append(pd.json_normalize(chunk, sep="."))
    df = pd.concat(chunks, ignore_index=True)

    # remove NaN Values
    rows_total = len(df)
    df = df.dropna()
    rows_no_nan = len(df)
    nan_removed = rows_total - rows_no_nan
    logger.info(f"Number of option chains: {rows_no_nan}. Removed {nan_removed} rows with NaN from {rows_total} rows.")

    df.rename(columns={ "details.ticker": "option_osi", 
                        "underlying_asset.ticker": "symbol",
                        "details.contract_type": "contract_type",
                        "details.expiration_date": "expiration_date",
                        "details.strike_price": "strike_price",
                        "details.exercise_style": "exercise_style",
                        "details.shares_per_contract": "shares_per_contract",
                        "greeks.delta": "greeks_delta",   
                        "greeks.gamma": "greeks_gamma",
                        "greeks.theta": "greeks_theta",
                        "greeks.vega": "greeks_vega",
                        "day.change": "day_change",
                        "day.change_percent": "day_change_percent",
                        "day.close": "day_close",
                        "day.high": "day_high",
                        "day.low": "day_low",
                        "day.open": "day_open",
                        "day.previous_close": "day_previous_close",
                        "day.volume": "day_volume",
                        "day.vwap": "day_vwap",
                        "day.last_updated": "day_last_updated"
                       }, inplace=True)

    # Remove "O:" prefix from details.ticker
    df["option_osi"] = df["option_osi"].str.replace("^O:", "", regex=True)

    # Convert timestamps in a vectorized way
    df["day_last_updated"] = (
        pd.to_datetime(df["day_last_updated"], unit='ns', utc=True)
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

def load_option_chains(symbols):
    logger.info(f"Loading for {len(symbols)} symbols option data from Massive API")

    conn = get_postgres_engine().raw_connection()
    try:
        truncate_table(conn, TABLE_OPTION_DATA_MASSIVE)

        # load batches of option chains for symbols
        batch_size = 1000
        total_options = 0
        symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
        batch = 1
        for symbol_batch in symbol_batches:
            if len(symbols) > batch_size:
                logger.info(f"({batch}/{len(symbol_batches)}) Fetching Massive API option data for batch of {len(symbol_batch)} symbols...")
                batch += 1
            df = get_option_chains_df(tickers=symbol_batch)

            insert_into_table_bulk(
                conn,
                table_name=TABLE_OPTION_DATA_MASSIVE,
                dataframe=df,
                if_exists="append"
            )

            total_options += len(df)
        
        conn.commit()
    finally:
        conn.close()
    logger.info(f"Total options collected and saved from Massive API: {total_options}")

    calculate_and_store_stock_implied_volatility()


def get_symbols(include: str | None = None) -> list | dict[str, list]:
    """
    Returns a list or dictionary of stock symbols, indices, and symbols with options.
    Optionally, you can specify which list to return.

    :param include: Optional string specifying which symbol list to return.
                    Possible values: "all", "stocks", "indices", "options", "stocks_with_exchange"
                    If None, returns a dictionary with all lists.
                    "stocks_with_exchange" is special it is a dict with key = symbol and value the exchange.
    :return: List or dictionary with keys: "all", "stocks", "indices", "options", "stocks_with_exchange"
    """

    logger.info("Loading symbols from database...")
    symbols = select_into_dataframe(f'SELECT symbol FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}"').squeeze().tolist()
    if len(symbols) == 0:
        load_symbols()
        symbols = select_into_dataframe(f'SELECT symbol FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}"').squeeze().tolist()
    
    option_symbols = select_into_dataframe(f'SELECT symbol FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}" WHERE has_options = true').squeeze().tolist()
    symbols_exchange = select_into_dataframe(f"""
                                             SELECT 
                                                symbol,
                                                CASE 
                                                    WHEN exchange_mic = 'XNAS' THEN 'NASDAQ'
                                                    WHEN exchange_mic = 'XNYS' OR exchange_mic = 'ARCX' THEN 'NYSE'
                                                    WHEN exchange_mic = 'XASE' THEN 'AMEX'
                                                    ELSE exchange_mic
                                                END AS exchange
                                             FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}"
                                             """)

    symbols_exchange.set_index('symbol').to_dict()

    logger.info(f"Loaded {len(symbols)} stock symbols, {len(option_symbols)} symbols with options and exchange info for {len(symbols_exchange)} symbols from the database.")

    result = {
        "all": symbols,
        "stocks": symbols,
        "indices": [], # not needed currently
        "options": option_symbols,
        "stocks_with_exchange": symbols_exchange
    }

    if include is not None:
        return sorted(list(set(result[include])))
    return result

def load_symbols():
    """
    Returns a list or dictionary of stock symbols, indices, and symbols with options.
    Optionally, you can specify which list to return.

    :param include: Optional string specifying which symbol list to return.
                    Possible values: "all", "stocks", "indices", "options", "stocks_with_exchange"
                    If None, returns a dictionary with all lists.
                    "stocks_with_exchange" is special it is a dict with key = symbol and value the exchange.
    :return: List or dictionary with keys: "all", "stocks", "indices", "options", "stocks_with_exchange"
    """
    logger.info("Loading symbols from Massive API...")

    all_symbols_stock_indices = asyncio.run(get_all_stocks_and_indices())
    # symbols_stocks = all_symbols_stock_indices["stocks"]
    # symbols_indices = all_symbols_stock_indices["indices"]
    stocks_with_exchange = all_symbols_stock_indices["stocks_with_exchange"]
    symbols_with_options = asyncio.run(get_active_tickers_with_options())

    df = pd.DataFrame(stocks_with_exchange.items(), columns=["symbol", "exchange_mic"])
    df["has_options"] = df["symbol"].apply(lambda x: x in symbols_with_options)
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_SYMBOLS_MASSIVE)
        insert_into_table(
            connection,
            table_name= TABLE_STOCK_SYMBOLS_MASSIVE,
            dataframe=df,
            if_exists="append"
        )
    logger.info(f"Loaded {len(df)} stock symbols with exchange and options info into the database.")

if __name__ == "__main__":
    # logging not needed when run from main
    setup_logging(log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info("Start Massiv API test")

    #symbols = get_symbols("all")

    a =  asyncio.run(get_all_stocks_and_indices())

    #all_tickers = asyncio.run(get_all_stocks_and_indices())
    # tickers_with_options = asyncio.run(get_active_tickers_with_options())
    # df = get_option_chains_df(tickers=tickers_with_options)
    pass


"""
https://massive.com/docs/rest/options/snapshots/option-chain-snapshot 

all_tickers["stocks"] enthält alle aktien -> brauchen wir

tickers_with_options enthält alle ticker(aktien, index, rohstoffe etc.) mit optionen -> brauchen wir

Set aus den beiden bilden. 
Benötigt Flag für Symbole mit Optionen um bei Strategien schnell filtern zu können.

get_option_chains_df(tickers=tickers_with_options) -> Liefert Optionspreise und Griechen

Benötigt täglich:
'implied_volatility', 
'open_interest', 
'greeks.delta', 
'greeks.gamma', 
'greeks.theta', 
'greeks.vega',
'day.close', (optionspreis aktuell)
'day.volume', 

Stammdaten benötigt
'details.contract_type',
'details.exercise_style', 
'details.expiration_date',
'details.shares_per_contract', 
'details.strike_price', 
'details.ticker', (enthält OPRA)
'underlying_asset.ticker',  (Symbol)

Aktuell nicht benötigt:
'day.change', 
'day.change_percent',
'day.high', 
'day.last_updated',  (Timestamp)
'day.low', 
'day.open',
'day.previous_close', 
'day.vwap',
'day.last_updated_humanreadable'
"""

