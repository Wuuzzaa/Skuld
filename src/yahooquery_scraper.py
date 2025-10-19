from datetime import datetime
import sys
import os
import time

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from yahooquery import Ticker
from config_utils import get_filtered_symbols_with_logging
from src.util import Singleton

# https://yahooquery.dpguthrie.com/guide/ticker/modules/
MODULES = 'calendarEvents summaryDetail financialData earningsTrend defaultKeyStatistics price'

@Singleton
class YahooQueryScraper:
    def __init__(self):
        self.symbols = get_filtered_symbols_with_logging("YahooQueryScraper")
        # Symbole in 500er-Pakete aufteilen
        self.batch_size = 500
        self.retries = 5
        self.symbol_batches = [self.symbols[i:i + self.batch_size] for i in range(0, len(self.symbols), self.batch_size)]
        print(f"Initializing {len(self.symbol_batches)} ticker batches")
        # asynchronous=True, max_workers=2, is not possible because of the high number of symbols and the rate limit
        self.ticker_batches = [Ticker(symbol_batch, progress=True) for symbol_batch in self.symbol_batches]
        self._module_data_cache = None
        self._module_data_cache_timestamp = None
        self._financial_data_cache = None
        print('YahooQueryScraper created')

    def _load_module_data(self, force_refresh=False):
        all_data = {}
        if self._module_data_cache is None or force_refresh:
            print(f"Loading for {len(self.symbols)} symbols module data from Yahoo Finance - modules: {MODULES}")
            for ticker_batch in self.ticker_batches:
                for attempt in range(self.retries):
                    try:
                        if len(self.symbols) > self.batch_size:
                            print(f"Fetching Yahoo module data for batch of up to {self.batch_size} symbols...")
                        data = ticker_batch.get_modules(MODULES)
                        all_data.update(data)
                    except Exception as e:
                        print(f"ERROR: Error fetching module data - {str(e)}")
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

            if all_data is None:
                print("WARNING: No module data found for any symbols")
                return
            self._module_data_cache_timestamp = datetime.now()
            self.validate_module_data(all_data)
            self._module_data_cache = all_data
        else:
            print(f"Using cached Yahoo Fiance module data - symbols: {len(self.symbols)} modules: {MODULES}")
            print(f"Cache age: {int((datetime.now() - self._module_data_cache_timestamp).total_seconds())} seconds")
        
        print(f"{len(self._module_data_cache)} symbols with module data")
        return self._module_data_cache
    
    def _load_all_financial_data(self, force_refresh=False):
        all_data = []
        if self._financial_data_cache is None or force_refresh:    
            print(f"Loading for {len(self.symbols)} symbols all financial data from Yahoo Finance")
            for ticker_batch in self.ticker_batches:
                for attempt in range(self.retries):
                    try:
                        if len(self.symbols) > self.batch_size:
                            print(f"Fetching Yahoo all financial data for batch of up to {self.batch_size} symbols...")
                        df = ticker_batch.all_financial_data()
                        df.reset_index(inplace=True)
                        if df is not None and not df.empty:
                            all_data.append(df)
                            print(f"SUCCESS: {len(df)} financial data found")
                        else:
                            print(f"WARNING: No option data available")
                    except Exception as e:
                        # e.g. Failed to perform, curl: (28) Operation timed out after 30002 milliseconds with 0 bytes received. See https://curl.se/libcurl/c/libcurl-errors.html first for more details.
                        print(f"ERROR: Error fetching all financial data - {str(e)}")
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

            if all_data is None:
                print("WARNING: No financial data found for any symbols")
                return
            df = pd.concat(all_data)
            self._financial_data_cache = df
        else:
            print(f"Using cached Yahoo Fiance financial data - symbols: {len(self.symbols)}")
        print(f"{len(self._financial_data_cache)} financial data entries")
        return self._financial_data_cache

    def get_modules(self, force_refresh=False):
        data = self._load_module_data(force_refresh)
        return data

    def get_modules_cache_timestamp(self):
        return self._module_data_cache_timestamp
    
    def get_all_financial_data(self, force_refresh=False):
        data = self._load_all_financial_data(force_refresh)
        return data
    
    def get_option_chain(self):
        print(f"Loading for {len(self.symbols)} symbols option chain from Yahoo Finance")
        all_option_data = []
        for ticker_batch in self.ticker_batches:
            for attempt in range(self.retries):
                try:
                    if len(self.symbols) > self.batch_size:
                        print(f"Fetching Yahoo option chain for batch of up to {self.batch_size} symbols...")
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
    
    def validate_module_data(self, module_data):
        symbols_to_be_deleted = []
        for symbol, symbol_data in module_data.items():
            if not isinstance(symbol_data, dict):
                # e.g. 'Quote not found for symbol: CHX'
                print(f"No valid data found for symbol {symbol}: {symbol_data}")
                print(f"Symbol {symbol} will be removed from the results")
                symbols_to_be_deleted.append(symbol)
        for symbol in symbols_to_be_deleted:
            del module_data[symbol]