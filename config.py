import pandas as pd
from dotenv import load_dotenv
import os
from pathlib import Path
from src.get_version import get_version

# first load the .env file - before usage of os.getenv()
load_dotenv()

# Massiv API
MASSIVE_API_KEY = os.getenv('MASSIVE_API_KEY')
MASSIVE_API_KEY_FLAT_FILES = os.getenv('MASSIVE_API_KEY_FLAT_FILES')
TEST_KEY= os.getenv('TEST_KEY') # DEBUG

# PostgreSQL
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')
POSTGRES_USER = os.getenv('POSTGRES_USER')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')

# SSH
SSH_HOST = os.getenv('SSH_HOST')
SSH_USER = os.getenv('SSH_USER')
SSH_PKEY_PATH = os.getenv('SSH_PKEY_PATH')

# Base path relative to base folder
BASE_DIR = Path(__file__).resolve().parent

VERSION = get_version(BASE_DIR)

# Logfile
PATH_LOGS_DIR = BASE_DIR / "logs"

# Filename merged dataframe the final file for the streamlit app
FILENAME_MERGED_DATAFRAME = 'merged_df.feather'
 
# Database
DATABASE_FILENAME = 'financial_data.db'
PATH_DATABASE_FOLDER = BASE_DIR / 'db'
PATH_DATABASE_FILE = PATH_DATABASE_FOLDER / DATABASE_FILENAME
PATH_DATABASE_QUERY_FOLDER = PATH_DATABASE_FOLDER / 'SQL' / 'query'

# Tables
TABLE_OPTION_DATA_TRADINGVIEW = 'OptionDataTradingView'
TABLE_OPTION_DATA_YAHOO = 'OptionDataYahoo'
TABLE_OPTION_DATA_MASSIVE = 'OptionDataMassive'
TABLE_ANALYST_PRICE_TARGETS = 'AnalystPriceTargets'
TABLE_EARNING_DATES = 'EarningDates'
TABLE_FUNDAMENTAL_DATA_DIVIDEND_RADAR = 'FundamentalDataDividendRadar'
TABLE_FUNDAMENTAL_DATA_YAHOO = 'FundamentalDataYahoo'
TABLE_TECHNICAL_INDICATORS = 'TechnicalIndicators'
TABLE_STOCK_PRICE = 'StockPrice'
TABLE_STOCK_PRICES_YAHOO = 'StockPricesYahoo'
TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE = 'StockImpliedVolatilityMassive'
TABLE_STOCK_SYMBOLS_MASSIVE = 'StockSymbolsMassive'
TABLE_STOCK_ASSET_PROFILES_YAHOO = 'StockAssetProfilesYahoo'
TABLE_DIVIDEND_DATA_YAHOO = 'DividendDataYahoo'

# History enabled tables
HISTORY_ENABLED_TABLES = [
    TABLE_EARNING_DATES,
    TABLE_OPTION_DATA_MASSIVE,
    TABLE_ANALYST_PRICE_TARGETS,
    TABLE_FUNDAMENTAL_DATA_DIVIDEND_RADAR,
    TABLE_TECHNICAL_INDICATORS,
    TABLE_FUNDAMENTAL_DATA_YAHOO,
    TABLE_STOCK_PRICES_YAHOO,
    TABLE_STOCK_IMPLIED_VOLATILITY_MASSIVE,
    TABLE_STOCK_ASSET_PROFILES_YAHOO,
    TABLE_DIVIDEND_DATA_YAHOO
]

#Views
VIEW_OPTION_DATA = 'OptionData'
VIEW_FUNDAMENTAL_DATA = 'FundamentalData'
VIEW_OPTION_DATA_MERGED = 'OptionDataMerged'
VIEW_OPTION_PRICING_METRICS = 'OptionPricingMetrics'
VIEW_STOCK_DATA = 'StockData'

HISTORY_ENABLED_VIEWS = [
    VIEW_OPTION_DATA,
    VIEW_FUNDAMENTAL_DATA,
    VIEW_OPTION_DATA_MERGED,
    VIEW_OPTION_PRICING_METRICS,
    VIEW_STOCK_DATA
]
 
 # Dividend Radar
URL_DIVIDEND_RADAR = "https://www.portfolio-insight.com/dividend-radar"

# App Logfile
PATH_APP_LOGFILE = BASE_DIR / 'app.log'

# Symbols excel file
PATH_SYMBOLS_EXCHANGE_FILE = BASE_DIR / 'symbols_exchange.xlsx'

# Symbols and exchange
df =pd.read_excel(PATH_SYMBOLS_EXCHANGE_FILE)
SYMBOLS_EXCHANGE = dict(zip(df['symbol'], df['exchange']))

SYMBOLS = list(SYMBOLS_EXCHANGE.keys())

# monte_carlo_simulator
RANDOM_SEED=42
IV_CORRECTION_MODE= 'auto'
RISK_FREE_RATE = 0.03
NUM_SIMULATIONS = 100000
TRANSACTION_COST_PER_CONTRACT = 2.0 # in USD

MAX_WORKERS = int(os.getenv('MAX_WORKERS') if os.getenv('MAX_WORKERS') else 1)  # Max number of parallel workers for data collection



