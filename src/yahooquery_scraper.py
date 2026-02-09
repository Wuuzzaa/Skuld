import logging
import sys
import os
import time
import threading
import pandas as pd
from yahooquery import Ticker
from src.util import Singleton
from datetime import datetime

logger = logging.getLogger(__name__)

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# https://yahooquery.dpguthrie.com/guide/ticker/modules/
MODULES = 'calendarEvents summaryDetail financialData earningsTrend defaultKeyStatistics price'

@Singleton
class YahooQueryScraper:
    def __init__(self, symbols):
        self.symbols = symbols
        # Symbole in 100er-Pakete aufteilen
        self.batch_size = 100
        self.retries = 5
        self.symbol_batches = [self.symbols[i:i + self.batch_size] for i in range(0, len(self.symbols), self.batch_size)]
        logger.info(f"Initializing {len(self.symbol_batches)} ticker batches with batch size {self.batch_size} for YahooQueryScraper - total symbols: {len(self.symbols)}")
        # asynchronous=True, max_workers=2, is not possible because of the high number of symbols and the rate limit
        self.ticker_batches = [Ticker(symbol_batch, progress=True) for symbol_batch in self.symbol_batches]
        
        self._module_data_cache = None
        self.module_data_lock = threading.Lock()
        self._module_data_cache_timestamp = None
       
        self.all_financial_data_lock = threading.Lock()

        logger.info('YahooQueryScraper created')

    def _load_module_data(self, force_refresh=False):
        with self.module_data_lock:
            all_data = {}
            if self._module_data_cache is None or force_refresh:
                logger.info(f"Loading for {len(self.symbols)} symbols module data from Yahoo Finance - modules: {MODULES}")
                batch = 1
                for ticker_batch in self.ticker_batches:
                    logger.info(f"({batch}/{len(self.ticker_batches)}) Batch")
                    batch += 1
                    for attempt in range(self.retries):
                        try:
                            if len(self.symbols) > self.batch_size:
                                logger.info(f"Fetching Yahoo module data for batch of up to {self.batch_size} symbols...")
                            data = ticker_batch.get_modules(MODULES)
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
                    # time.sleep(1)

                if all_data is None:
                    logger.warning("WARNING: No module data found for any symbols")
                    return
                self._module_data_cache_timestamp = datetime.now()
                self.validate_module_data(all_data)
                self._module_data_cache = all_data
            else:
                logger.info(f"Using cached Yahoo Fiance module data - symbols: {len(self.symbols)} modules: {MODULES}")
                logger.info(f"Cache age: {int((datetime.now() - self._module_data_cache_timestamp).total_seconds())} seconds")
            
            logger.info(f"{len(self._module_data_cache)} symbols with module data")
            return self._module_data_cache
    
    def _load_all_financial_data(self, force_refresh=False):
        with self.all_financial_data_lock:
            all_data = [] 
            batch = 1
            logger.info(f"Loading for {len(self.symbols)} symbols all financial data from Yahoo Finance")
            for ticker_batch in self.ticker_batches:
                logger.info(f"({batch}/{len(self.ticker_batches)}) Batch")
                batch += 1
                for attempt in range(self.retries):
                    try:
                        if len(self.symbols) > self.batch_size:
                            logger.info(f"Fetching Yahoo all financial data for batch of up to {self.batch_size} symbols...")
                        df = ticker_batch.all_financial_data()
                        df.reset_index(inplace=True)
                        if df is not None and not df.empty:
                            all_data.append(df)
                            logger.info(f"SUCCESS: {len(df)} financial data found")
                        else:
                            logger.warning(f"WARNING: No option data available")
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
                # time.sleep(1)

            if all_data is None:
                logger.warning("WARNING: No financial data found for any symbols")
                return
            df = pd.concat(all_data)
            
            logger.info(f"{len(df)} financial data entries")
            df.info(memory_usage='deep')
            return df

    def get_historical_prices(self, period="1d"):
        found_data = False
        batch = 1
        for ticker_batch in self.ticker_batches:
            logger.info(f"({batch}/{len(self.ticker_batches)}) Batch")
            batch += 1
            for attempt in range(self.retries):
                try:
                    if len(self.symbols) > self.batch_size:
                        logger.info(f"Fetching Yahoo historical data for batch of up to {self.batch_size} symbols...")
                    df = ticker_batch.history(period=period, interval='1d')
                    if df is not None and not df.empty:
                        # symbol expiration_date and option-type from index to column
                        df = df.reset_index()
                        found_data = True
                        logger.info(f"SUCCESS: {len(df)} historical prices found")
                        yield df
                    else:
                        logger.warning(f"WARNING: No historical prices available")

                except Exception as e:
                    logger.error(f"ERROR: Error fetching historical prices - {str(e)}")
                    logger.error(f"{attempt} failed -> Retry after 10s")
                    time.sleep(10)
                else:
                    # Success - exit the retry loop
                    break
            else:
                logger.error(" ! " * 80)
                logger.error("RETRY LIMIT REACHED")
                logger.error(" ! " * 80)

    def get_modules(self, force_refresh=False):
        data = self._load_module_data(force_refresh)
        return data

    def get_modules_cache_timestamp(self):
        return self._module_data_cache_timestamp
    
    def get_all_financial_data(self, force_refresh=False):
        data = self._load_all_financial_data(force_refresh)
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