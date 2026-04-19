import logging
import pandas as pd
import asyncio
import aiohttp
from typing import Union, List, Dict, Optional
from tqdm import tqdm
from config import MASSIVE_API_KEY, TABLE_OPTION_DATA_MASSIVE, TABLE_STOCK_SYMBOLS_MASSIVE
from src.database import get_postgres_engine, truncate_table, insert_into_table, insert_into_table_bulk, select_into_dataframe
from src.decorator_log_function import log_function
from src.logger_config import setup_logging
from src.stock_volatility import calculate_and_store_stock_implied_volatility

logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://api.massive.com/v3"
DEFAULT_CONNECTOR_LIMIT = 20
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=600)

def get_session(connector_limit: int = DEFAULT_CONNECTOR_LIMIT, timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT) -> aiohttp.ClientSession:
    connector = aiohttp.TCPConnector(limit=connector_limit)
    return aiohttp.ClientSession(connector=connector, timeout=timeout)

async def _fetch_paginated_data(url: str, params: Dict[str, Union[str, int]], session: aiohttp.ClientSession, description: str = "data") -> List[dict]:
    """
    General helper to fetch paginated data from Massive API.
    """
    all_results = []
    current_url = url
    current_params = params.copy()

    try:
        while current_url:
            async with session.get(current_url, params=current_params) as response:
                data = await response.json()

                if data.get('status') != 'OK':
                    logger.error(f"Error fetching {description}: {data.get('error')}")
                    break

                results = data.get('results', [])
                all_results.extend(results)

                next_url = data.get('next_url')
                if next_url:
                    current_url = next_url
                    current_params = {"apiKey": MASSIVE_API_KEY}
                else:
                    current_url = None

        return all_results

    except Exception as e:
        logger.exception(f"Exception fetching {description}: {e}")
        return all_results

async def _fetch_tickers(market: str, session: aiohttp.ClientSession, include_exchange: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
    """
    Fetches tickers from Massive API for a specific market.
    """
    url = f"{BASE_URL}/reference/tickers"
    params = {
        "market": market,
        "active": "true",
        "order": "asc",
        "limit": 1000,
        "sort": "ticker",
        "apiKey": MASSIVE_API_KEY
    }

    results = await _fetch_paginated_data(url, params, session, description=f"tickers for {market}")
    
    if market == "stocks":
        results = [item for item in results if item.get('type') in ['CS', 'ETF']]

    if include_exchange:
        return {
            item.get('ticker'): {
                'primary_exchange': item.get('primary_exchange'),
                'type': item.get('type')
            } 
            for item in results if item.get('ticker')
        }
    else:
        return [item.get('ticker') for item in results if item.get('ticker')]

@log_function
async def get_all_stocks_and_indices():
    """
    Fetches all stock and index tickers, including exchange information for stocks.
    """
    async with get_session() as session:
        # Fetch stocks with exchange (provides both symbol list and mapping)
        stocks_with_exchange_task = _fetch_tickers("stocks", session, include_exchange=True)
        indices_task = _fetch_tickers("indices", session)

        stocks_with_exchange, indices = await asyncio.gather(
            stocks_with_exchange_task, indices_task
        )

    stocks = list(stocks_with_exchange.keys())
    all_tickers = stocks + indices

    return {
        "all": all_tickers,
        "stocks": stocks,
        "indices": indices,
        "stocks_with_exchange": stocks_with_exchange
    }

async def _fetch_option_chain_chunk(ticker: str, session: aiohttp.ClientSession, limit: int = 250) -> List[dict]:
    """
    Fetches all option chains for a specific ticker from the Massive API.
    """
    url = f"{BASE_URL}/snapshot/options/{ticker}"
    params = {
        "limit": limit,
        "apiKey": MASSIVE_API_KEY
    }
    return await _fetch_paginated_data(url, params, session, description=f"option chains for {ticker}")

async def _check_has_options(ticker: str, session: aiohttp.ClientSession) -> Optional[str]:
    """Check if a single ticker has any options."""
    url = f"{BASE_URL}/snapshot/options/{ticker}"
    params = {"limit": 1, "apiKey": MASSIVE_API_KEY}
    try:
        async with session.get(url, params=params) as response:
            data = await response.json()
            if data.get('status') == 'OK' and data.get('results'):
                return ticker
    except Exception:
        pass
    return None

@log_function
async def get_active_tickers_with_options():
    """
    Retrieves a list of all active stock and index tickers that have available option chains.
    """
    async with get_session(timeout=aiohttp.ClientTimeout(total=1800)) as session:
        # Fetch active tickers for stocks and indices in parallel
        stocks_task = _fetch_tickers("stocks", session)
        indices_task = _fetch_tickers("indices", session)
        
        stocks, indices = await asyncio.gather(stocks_task, indices_task)
        all_tickers = stocks + indices

        # Check in batches if they have options
        batch_size = 50  # Increased batch size
        tickers_with_options = []

        for i in range(0, len(all_tickers), batch_size):
            batch = all_tickers[i:i + batch_size]
            tasks = [_check_has_options(ticker, session) for ticker in batch]
            results = await asyncio.gather(*tasks)
            tickers_with_options.extend([r for r in results if r is not None])
            
    return sorted(tickers_with_options)

@log_function
def _option_chains_to_dataframe(option_chains: List[dict]) -> pd.DataFrame:
    """
    Flatten a list of nested dictionaries (option_chains) into a Pandas DataFrame.
    """
    if not option_chains:
        return pd.DataFrame()

    chunks = []
    chunk_size = 1000
    for i in tqdm(range(0, len(option_chains), chunk_size), desc="Processing option chains"):
        chunk = option_chains[i:i + chunk_size]
        chunks.append(pd.json_normalize(chunk, sep="."))
    df = pd.concat(chunks, ignore_index=True)

    rows_total = len(df)
    df = df.dropna()
    nan_removed = rows_total - len(df)
    logger.info(f"Number of option chains: {len(df)}. Removed {nan_removed} rows with NaN from {rows_total} rows.")

    column_mapping = {
        "details.ticker": "option_osi",
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
    }
    df.rename(columns=column_mapping, inplace=True)

    if "option_osi" in df.columns:
        df["option_osi"] = df["option_osi"].str.replace("^O:", "", regex=True)

    if "day_last_updated" in df.columns:
        df["day_last_updated"] = pd.to_datetime(df["day_last_updated"], unit='ns', utc=True)

    return df

async def _fetch_option_chains_tickers_async(tickers: List[str], limit: int = 250) -> List[dict]:
    """
    Fetches all option chains for a list of tickers in parallel.
    """
    async with get_session() as session:
        tasks = [_fetch_option_chain_chunk(ticker, session, limit) for ticker in tickers]
        results = await asyncio.gather(*tasks)

    option_chains = [item for sublist in results for item in sublist]

    if not option_chains:
        logger.error("No option chains data found for any tickers")
        raise Exception("No option chains data found for any tickers")
    
    return option_chains

@log_function
def get_option_chains_df(tickers: Union[List[str], str] = "auto", limit: int = 250) -> pd.DataFrame:
    """
    Fetches option chains for a list of tickers and returns the data as a pandas DataFrame.
    """
    if tickers == "auto":
        tickers = asyncio.run(get_active_tickers_with_options())
    
    option_chains = asyncio.run(_fetch_option_chains_tickers_async(tickers, limit=limit))
    return _option_chains_to_dataframe(option_chains)

def load_option_chains(symbols: List[str]):
    """
    Loads option data for given symbols from Massive API and saves to database.
    """
    logger.info(f"Loading option data for {len(symbols)} symbols from Massive API")

    engine = get_postgres_engine()
    with engine.raw_connection() as conn:
        try:
            truncate_table(conn, TABLE_OPTION_DATA_MASSIVE)

            batch_size = 1000
            total_options = 0
            
            for i in range(0, len(symbols), batch_size):
                symbol_batch = symbols[i:i + batch_size]
                logger.info(f"Fetching Massive API option data for batch {i//batch_size + 1}...")
                
                df = get_option_chains_df(tickers=symbol_batch)

                if not df.empty:
                    insert_into_table_bulk(
                        conn,
                        table_name=TABLE_OPTION_DATA_MASSIVE,
                        dataframe=df,
                        if_exists="append"
                    )
                    total_options += len(df)
            
            conn.commit()
            logger.info(f"Successfully saved {total_options} options to {TABLE_OPTION_DATA_MASSIVE}")
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to load option chains: {e}")
            raise

    calculate_and_store_stock_implied_volatility()

def get_symbols(include: Optional[str] = None) -> Union[List[str], Dict[str, List[str]]]:
    """
    Returns a list or dictionary of stock symbols, indices, and symbols with options.
    """
    logger.info("Loading symbols from database...")
    df = select_into_dataframe(f'SELECT symbol, has_options, type FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}" ORDER BY symbol')
    
    if df.empty:
        load_symbols()
        df = select_into_dataframe(f'SELECT symbol, has_options, type FROM "{TABLE_STOCK_SYMBOLS_MASSIVE}" ORDER BY symbol')
    
    result = {
        "all": df["symbol"].tolist(),
        "stocks": df[df["type"] == "stock"]["symbol"].tolist(),
        "indices": df[df["type"] == "index"]["symbol"].tolist(),
        "options": df[df["has_options"] == True]["symbol"].tolist()
    }

    if include is not None:
        return sorted(list(set(result[include])))
    return result

def load_symbols():
    """
    Refreshes the symbols database from the Massive API.
    """
    logger.info("Loading symbols from Massive API...")

    all_data = asyncio.run(get_all_stocks_and_indices())
    symbols_with_options = asyncio.run(get_active_tickers_with_options())

    # Stocks & ETFs
    stocks_data = []
    for symbol, info in all_data["stocks_with_exchange"].items():
        stocks_data.append({
            "symbol": symbol,
            "exchange_mic": info["primary_exchange"],
            "type": "stock" if info["type"] == "CS" else "etf"
        })
    df_stocks = pd.DataFrame(stocks_data)

    # Indices DF
    df_indices = pd.DataFrame(all_data["indices"], columns=["symbol"])
    df_indices["exchange_mic"] = None
    df_indices["type"] = "index"

    # Combine and deduplicate
    df = pd.concat([df_stocks, df_indices], ignore_index=True).drop_duplicates(subset=["symbol"])
    df["has_options"] = df["symbol"].isin(symbols_with_options)

    # Note: Indices might have prefixes like I:SPX (handled by Massive API)

    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_SYMBOLS_MASSIVE)
        insert_into_table(
            connection,
            table_name=TABLE_STOCK_SYMBOLS_MASSIVE,
            dataframe=df,
            if_exists="append"
        )
    logger.info(f"Loaded {len(df)} symbols with exchange and options into the database.")

if __name__ == "__main__":
    setup_logging(log_level=logging.DEBUG, console_output=True)
    logger = logging.getLogger(__name__)
    logger.info("Start Massive API test")

    # chains = get_option_chains_df()
    # symbols = get_symbols("options")
    load_symbols()

