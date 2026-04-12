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

async def __get_tickers_from_api(market: str, session: aiohttp.ClientSession, include_exchange: bool = False) -> Union[List[str], dict]:
    """
    General helper to fetch tickers from Massive API for a specific market.
    :param market: 'stocks' or 'indices'
    :param session: aiohttp session
    :param include_exchange: if True, returns a dict {symbol: exchange}, otherwise a list [symbol]
    :return: List of tickers or Dictionary with ticker: exchange mapping
    """
    url = "https://api.massive.com/v3/reference/tickers"
    params = {
        "market": market,
        "active": "true",
        "order": "asc",
        "limit": 1000,
        "sort": "ticker",
        "apiKey": MASSIVE_API_KEY
    }

    results_data = {} if include_exchange else []
    
    while url:
        async with session.get(url, params=params) as response:
            data = await response.json()

            if data.get('status') != 'OK':
                logger.error(f"Error fetching tickers for {market}: {data.get('error')}")
                break

            results = data.get('results', [])

            for ticker_data in results:
                ticker = ticker_data.get('ticker')
                if not ticker:
                    continue
                
                if include_exchange:
                    results_data[ticker] = ticker_data.get('primary_exchange')
                else:
                    results_data.append(ticker)

            next_url = data.get('next_url')
            if next_url:
                url = next_url
                params = {"apiKey": MASSIVE_API_KEY}
            else:
                url = None

    return results_data

@log_function
async def get_all_stocks_and_indices():
    """
    Fetches all stock and index tickers, including exchange information for stocks.
    """
    connector = aiohttp.TCPConnector(limit=20)
    timeout = aiohttp.ClientTimeout(total=600)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        stocks_task = __get_tickers_from_api("stocks", session)
        indices_task = __get_tickers_from_api("indices", session)
        stocks_with_exchange_task = __get_tickers_from_api("stocks", session, include_exchange=True)

        stocks, indices, stocks_with_exchange = await asyncio.gather(
            stocks_task, indices_task, stocks_with_exchange_task
        )

    all_tickers = stocks + indices

    return {
        "all": all_tickers,
        "stocks": stocks,
        "indices": indices,
        "stocks_with_exchange": stocks_with_exchange
    }

async def __get_all_option_chains_for_ticker(ticker, session, limit=250):
    """
    Fetches all option chains for a specific ticker from the Massive API.
    """
    all_results = []
    url = f"https://api.massive.com/v3/snapshot/options/{ticker}"
    params = {
        "limit": limit,
        "apiKey": MASSIVE_API_KEY
    }

    try:
        while url:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if data.get('status') != 'OK':
                    logger.error(f"{ticker}: Error fetching option chains - {data.get('error')}")
                    # Break instead of raising to allow other tickers to continue in batch
                    break

                results = data.get('results', [])
                all_results.extend(results)

                next_url = data.get('next_url')
                if next_url:
                    url = next_url
                    params = {"apiKey": MASSIVE_API_KEY}
                else:
                    url = None

        return all_results

    except Exception as e:
        logger.exception(f"Exception fetching options for {ticker}: {e}")
        return []

async def __get_option_chains_tickers_async(tickers, limit=250):
    """
    Fetches all option chains for a list of tickers in parallel, including Greeks and IV.
    """
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

    if not option_chains:
        logger.error("No option chains data found for any tickers")
        raise Exception("No option chains data found for any tickers")
    
    return option_chains

@log_function
async def get_active_tickers_with_options():
    """
    Retrieves a list of all active stock and index tickers that have available option chains.
    """
    async def has_options(ticker, session):
        url = f"https://api.massive.com/v3/snapshot/options/{ticker}"
        params = {
            "limit": 1,
            "apiKey": MASSIVE_API_KEY
        }

        try:
            async with session.get(url, params=params) as response:
                data = await response.json()
                if data.get('status') == 'OK' and data.get('results'):
                    return ticker
        except Exception:
            pass
        return None

    connector = aiohttp.TCPConnector(limit=20)
    timeout = aiohttp.ClientTimeout(total=1800)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Fetch active tickers for stocks and indices parallel
        stocks_task = __get_tickers_from_api("stocks", session)
        indices_task = __get_tickers_from_api("indices", session)
        
        stocks, indices = await asyncio.gather(stocks_task, indices_task)
        all_tickers = stocks + indices

        # Check in batches if they have options
        batch_size = 20
        tickers_with_options = []

        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i + batch_size]
            tasks = [has_options(ticker, session) for ticker in batch]
            results = await asyncio.gather(*tasks)

            tickers_with_options.extend([r for r in results if r is not None])
            
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
    df = select_into_dataframe(f'SELECT symbol, has_options, type FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}" ORDER BY symbol')
    
    if len(df) == 0:
        load_symbols()
        df = select_into_dataframe(f'SELECT symbol, has_options, type FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}" ORDER BY symbol')
    
    symbols = df["symbol"].tolist()
    stock_symbols = df[df["type"] == "stock"]["symbol"].tolist()
    index_symbols = df[df["type"] == "index"]["symbol"].tolist()
    option_symbols = df[df["has_options"] == True]["symbol"].tolist()

    logger.info(f"Loaded {len(symbols)} total symbols, {len(stock_symbols)} stocks, {len(index_symbols)} indices, {len(option_symbols)} symbols with options from the database.")

    result = {
        "all": symbols,
        "stocks": stock_symbols,
        "indices": index_symbols,
        "options": option_symbols
    }

    if include is not None:
        return sorted(list(set(result[include])))
    return result

def get_symbols_with_exchange():
    """
    Fetches symbols with exchange mappings from the database.
    Normalizes exchange MIC codes to common names.
    """
    symbols_exchange = select_into_dataframe(f"""
                                             SELECT 
                                                symbol,
                                                CASE 
                                                    WHEN exchange_mic = 'XNAS' THEN 'NASDAQ'
                                                    WHEN exchange_mic = 'XNYS' THEN 'NYSE'
                                                    WHEN exchange_mic = 'ARCX' THEN 'AMEX'
                                                    WHEN exchange_mic = 'XASE' THEN 'AMEX'
                                                    ELSE exchange_mic
                                                END AS exchange
                                             FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}"
                                             WHERE symbol IN (SELECT symbol FROM "TechnicalIndicatorsMasterData" where from_date < '2026-02-16')
                                             ORDER BY symbol
                                             """)

    logger.info(f"Loaded {len(symbols_exchange)} symbols with exchange from the database.")
    return symbols_exchange

def load_symbols():
    """
    Refreshes the symbols database from the Massive API.
    Identifies which tickers have available options.
    """
    logger.info("Loading symbols from Massive API...")

    all_symbols_stock_indices = asyncio.run(get_all_stocks_and_indices())
    stocks_with_exchange = all_symbols_stock_indices["stocks_with_exchange"]
    indices = all_symbols_stock_indices["indices"]
    symbols_with_options = asyncio.run(get_active_tickers_with_options())

    # Create Stocks DataFrame
    df_stocks = pd.DataFrame(stocks_with_exchange.items(), columns=["symbol", "exchange_mic"])
    df_stocks["type"] = "stock"

    # Create Indices DataFrame
    df_indices = pd.DataFrame(indices, columns=["symbol"])
    df_indices["exchange_mic"] = None
    df_indices["type"] = "index"

    # Combine DataFrames
    df = pd.concat([df_stocks, df_indices], ignore_index=True)

    # Distinct symbols
    df = df.drop_duplicates(subset=["symbol"])

    # Update has_options column
    df["has_options"] = df["symbol"].apply(lambda x: x in symbols_with_options)

    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_SYMBOLS_MASSIVE)
        insert_into_table(
            connection,
            table_name=TABLE_STOCK_SYMBOLS_MASSIVE,
            dataframe=df,
            if_exists="append"
        )
    logger.info(f"Loaded {len(df)} symbols with exchange and options info into the database.")

if __name__ == "__main__":
    # logging not needed when run from main
    setup_logging(log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info("Start Massive API test")

    # chains = get_option_chains_df()
    # symbols = get_symbols("options")
    load_symbols()
    pass

