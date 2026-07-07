import gc
import logging
import sys
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import pandas as pd
import numpy as np
from yahooquery import Ticker
from config import MAX_WORKERS
from src.util import Singleton, log_memory_usage
from datetime import datetime

logger = logging.getLogger(__name__)

# Per-request timeout (seconds) - if a single Yahoo API call hangs longer than this, skip it
YAHOO_REQUEST_TIMEOUT = 600  # 10 minutes per batch request

# Executor for timeout-wrapped calls (daemon threads so they don't block exit)
_timeout_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yahoo_timeout")


def _call_with_timeout(fn, timeout_seconds=YAHOO_REQUEST_TIMEOUT, description="Yahoo API call"):
    """Execute fn() with a timeout. Returns None if timed out."""
    future = _timeout_executor.submit(fn)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        logger.error(f"TIMEOUT ({timeout_seconds}s): {description} — skipping this batch")
        return None
    except Exception as e:
        logger.error(f"ERROR in {description}: {e}")
        raise

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# https://yahooquery.dpguthrie.com/guide/ticker/modules/
MODULES = 'calendarEvents summaryDetail financialData earningsTrend defaultKeyStatistics price assetProfile'

@Singleton
class YahooQueryScraper:
    def __init__(self, symbols):
        # replace symbol prefix I: with ^ for indices to match yahoo format
        symbols = [symbol.replace('I:', '^') for symbol in symbols]
        self.symbols = symbols
        self.retries = 5
        self._module_data_cache = None
        self.module_data_lock = threading.Lock()
        self._module_data_cache_timestamp = None
       
        self.all_financial_data_lock = threading.Lock()

        logger.info('YahooQueryScraper created')

    def _load_module_data(self, symbols=None, modules=None):
        # if MAX_WORKERS == 1:
        if modules:
            ignore_cache = True
        else:
            ignore_cache=False
        if not modules:
            modules = MODULES
        if not symbols:
            symbols = self.symbols
        with self.module_data_lock:
            all_data = {}
            if self._module_data_cache is None:
                logger.info(f"Loading for {len(symbols)} symbols module data from Yahoo Finance - modules: {modules}")
                # Symbole in 2000er-Pakete aufteilen
                local_batch_size = 2000
                # asynchronous=True, max_workers=2, is not possible because of the high number of symbols and the rate limit
                local_ticker_batches = _get_ticker_batches(symbols, local_batch_size, self.retries, asynchronous=False)
                batch = 1
                for ticker_batch in local_ticker_batches:
                    logger.info(f"({batch}/{len(local_ticker_batches)}) Batch")
                    batch += 1
                    for attempt in range(self.retries):
                        try:
                            if len(symbols) > local_batch_size:
                                logger.info(f"Fetching Yahoo module data for batch of up to {local_batch_size} symbols...")
                            data = _call_with_timeout(
                                lambda tb=ticker_batch, m=modules: tb.get_modules(m),
                                timeout_seconds=YAHOO_REQUEST_TIMEOUT,
                                description=f"get_modules batch {batch-1}/{len(local_ticker_batches)}"
                            )
                            if data is None:
                                break  # timeout — skip this batch
                            all_data.update(data)
                        except Exception as e:
                            logger.error(f"ERROR: Error fetching module data - {str(e)}")
                            logger.error(f"{attempt} failed -> Retry after 10s")
                            time.sleep(10)
                        else: 
                            # Success - exit the retry loop
                            break
                    else:
                        logger.error(" ! " * 80)
                        logger.error("RETRY LIMIT REACHED")
                        logger.error(" ! " * 80)
                        raise Exception("RETRY LIMIT REACHED")

                if all_data is None:
                    logger.warning("WARNING: No module data found for any symbols")
                    return
                self.validate_module_data(all_data)
                if not ignore_cache:
                    self._module_data_cache_timestamp = datetime.now()
                    self._module_data_cache = all_data
            else:
                logger.info(f"Using cached Yahoo Fiance module data - symbols: {len(symbols)} modules: {modules}")
                logger.info(f"Cache age: {int((datetime.now() - self._module_data_cache_timestamp).total_seconds())} seconds")
            
            if ignore_cache:
                return all_data
            else:
                logger.info(f"{len(self._module_data_cache)} symbols with module data")
                return self._module_data_cache
    
    def _load_all_financial_data(self, symbols=None):
        if not symbols:
            symbols = self.symbols
        with self.all_financial_data_lock:
            all_data = []
            batch = 1
            logger.info(f"Loading for {len(symbols)} symbols all financial data from Yahoo Finance")
            # Symbole in 2000er-Pakete aufteilen
            local_batch_size = 2000
            local_ticker_batches = _get_ticker_batches(symbols, local_batch_size, self.retries, asynchronous=True)
            for ticker_batch in local_ticker_batches:
                logger.info(f"({batch}/{len(local_ticker_batches)}) Batch")
                batch += 1
                for attempt in range(self.retries):
                    try:
                        if len(symbols) > local_batch_size:
                            logger.info(f"Fetching Yahoo all financial data for batch of up to {local_batch_size} symbols...")
                        df = _call_with_timeout(
                            lambda tb=ticker_batch: tb.all_financial_data(),
                            timeout_seconds=YAHOO_REQUEST_TIMEOUT,
                            description=f"all_financial_data batch {batch-1}/{len(local_ticker_batches)}"
                        )
                        if df is None:
                            logger.warning(f"Batch {batch-1} timed out — skipping")
                            break  # timeout — skip this batch
                        df.reset_index(inplace=True)
                        if df is not None and not df.empty:
                            df_mem_mb = df.memory_usage(deep=True).sum() / 1024 / 1024
                            all_data.append(df)
                            total_rows = sum(len(d) for d in all_data)
                            logger.info(f"SUCCESS: {len(df)} rows fetched (DataFrame: {df_mem_mb:.1f} MB) | Total accumulated: {total_rows} rows")
                            log_memory_usage(f"[MEM] After all_financial_data batch {batch-1}/{len(local_ticker_batches)}: ")
                        else:
                            logger.warning(f"WARNING: No financial data available")
                    except Exception as e:
                        # e.g. Failed to perform, curl: (28) Operation timed out after 30002 milliseconds with 0 bytes received. See https://curl.se/libcurl/c/libcurl-errors.html first for more details.
                        logger.error(f"ERROR: Error fetching all financial data - {str(e)}")
                        logger.error(f"{attempt} failed -> Retry after 10s")
                        time.sleep(10)
                    else:
                        # Success - exit the retry loop
                        break
                else:
                    logger.error(" ! " * 80)
                    logger.error("RETRY LIMIT REACHED")
                    logger.error(" ! " * 80)
                    raise Exception("RETRY LIMIT REACHED")

            if all_data is None or len(all_data) == 0:
                logger.warning("WARNING: No financial data found for any symbols")
                return None
            df = pd.concat(all_data)

            logger.info(f"{len(df)} financial data entries")
            df.info(memory_usage='deep')

            return df

    def get_historical_prices(self, period="1d"):
        local_batch_size = 500
        local_ticker_batches = _get_ticker_batches(self.symbols, local_batch_size, self.retries, asynchronous=True)
        batch = 1
        for ticker_batch in local_ticker_batches:
            logger.info(f"({batch}/{len(local_ticker_batches)}) Batch")
            batch += 1
            for attempt in range(self.retries):
                try:
                    if len(self.symbols) > local_batch_size:
                        logger.info(f"Fetching Yahoo historical data for batch of up to {local_batch_size} symbols...")
                    # # Historical prices for 26y can be very slow — use longer timeout
                    hist_timeout = YAHOO_REQUEST_TIMEOUT * 3 if period != '1d' else YAHOO_REQUEST_TIMEOUT
                    # df = _call_with_timeout(
                    #     lambda tb=ticker_batch, p=period: tb.history(period=p, interval='1d'),
                    #     timeout_seconds=hist_timeout,
                    #     description=f"history(period={period}) batch {batch-1}/{len(local_ticker_batches)}"
                    # )
                    df = ticker_batch.history(period=period, interval='1d')
                    if df is None:
                        logger.warning(f"Batch {batch-1} timed out — skipping")
                        break  # timeout — skip this batch
                    if df is not None and not df.empty:
                        # symbol expiration_date and option-type from index to column
                        df = df.reset_index()
                        cols_cleanup = ['dividends', 'splits']
                        for col in cols_cleanup:
                            if col in df.columns:
                                df[col] = df[col].replace(0, np.nan)
                            else:
                                logger.warning(f"No column '{col}' in dataframe")
                        found_data = True
                        logger.info(f"SUCCESS: {len(df)} historical prices found")
                        yield df
                    else:
                        logger.warning(f"WARNING: No historical prices available")

                except Exception as e:
                    logger.error(f"Error fetching historical prices - {str(e)}")
                    logger.error(e)
                    logger.error(f"{attempt} failed -> Retry after 10s")
                    time.sleep(10)
                else:
                    # Success - exit the retry loop
                    break
            else:
                logger.error(" ! " * 80)
                logger.error("RETRY LIMIT REACHED")
                logger.error(" ! " * 80)
                raise Exception("RETRY LIMIT REACHED")

    def get_option_chain(self, symbols=None):
        print(f"Loading for {len(self.symbols)} symbols option chain from Yahoo Finance")
        if not symbols:
            symbols = self.symbols

        all_option_data = []
        local_batch_size = 500
        local_ticker_batches = _get_ticker_batches(symbols, local_batch_size, self.retries, asynchronous=False)
                
        for ticker_batch in local_ticker_batches:
            for attempt in range(self.retries):
                try:
                    if len(symbols) > local_batch_size:
                        print(f"Fetching Yahoo option chain for batch of up to {local_batch_size} symbols...")
                    df = ticker_batch.option_chain
                    if df is not None and not df.empty:
                        # symbol expiration_date and option-type from index to column
                        df = df.reset_index()
                        all_option_data.append(df)
                        print(f"SUCCESS: {len(df)} options found")
                    else:
                        print(f"WARNING: No option data available")
                        
                except Exception as e:
                    print(f"ERROR: Error fetching options - {str(e)}")
                    print(f"{attempt} failed -> Retry after 10s")
                    time.sleep(10)
                else: 
                    # Success - exit the retry loop
                    break
            else:
                print(" ! " * 80)
                print("RETRY LIMIT REACHED")
                print(" ! " * 80)
                time.sleep(1)

        if not all_option_data:
            print("WARNING: No option data found for any symbols")
            return
        
        # Combine all data
        df = pd.concat(all_option_data, ignore_index=True)
        print(f"{len(df)} option chains")
        return df
    
    def get_modules(self, symbols=None, modules=None):
        data = self._load_module_data(symbols=symbols, modules=modules)
        return data

    def get_modules_cache_timestamp(self):
        return self._module_data_cache_timestamp
    
    def get_all_financial_data(self, symbols=None):
        data = self._load_all_financial_data(symbols=symbols)
        return data

    def validate_module_data(self, module_data):
        symbols_to_be_deleted = []
        for symbol, symbol_data in module_data.items():
            if not isinstance(symbol_data, dict):
                # e.g. 'Quote not found for symbol: CHX'
                logger.warning(f"No valid data found for symbol {symbol}: {symbol_data}")
                logger.warning(f"Symbol {symbol} will be removed from the results")
                symbols_to_be_deleted.append(symbol)
        for symbol in symbols_to_be_deleted:
            del module_data[symbol]

def _get_ticker_batches(symbols, batch_size, retries, asynchronous=False):
    local_symbol_batches = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
    logger.info(f"Initializing {len(local_symbol_batches)} ticker batches with batch size {batch_size} for YahooQueryScraper - total symbols: {len(symbols)}")
    for attempt in range(retries):
        try:
            ticker_batches = [Ticker(symbol_batch, progress=True, asynchronous=asynchronous) for symbol_batch in local_symbol_batches]
        except Exception as e:
                logger.error(f"Error fetching historical prices - {str(e)}")
                logger.error(e)
                logger.error(f"{attempt} failed -> Retry after 10s")
                time.sleep(10)
        else:
                # Success - exit the retry loop
                break
    else:
            logger.error(" ! " * 80)
            logger.error("RETRY LIMIT REACHED")
            logger.error(" ! " * 80)
            raise Exception("RETRY LIMIT REACHED")
    
    return ticker_batches

