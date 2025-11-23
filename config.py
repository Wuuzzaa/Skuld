import pandas as pd
from pathlib import Path
from src.get_version import get_version


# Base path relative to base folder
BASE_DIR = Path(__file__).resolve().parent

VERSION = get_version(BASE_DIR)

# Logfile
PATH_LOG_FILE = BASE_DIR / "logs" /"log.log"

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
TABLE_ANALYST_PRICE_TARGETS = 'AnalystPriceTargets'
TABLE_EARNING_DATES = 'EarningDates'
TABLE_FUNDAMENTAL_DATA_DIVIDEND_RADAR = 'FundamentalDataDividendRadar'
TABLE_FUNDAMENTAL_DATA_YAHOO = 'FundamentalDataYahoo'
TABLE_FUNDAMENTAL_DATA_YAHOO_PROCESSED = 'FundamentalDataYahooProcessed'
TABLE_TECHNICAL_INDICATORS = 'TechnicalIndicators'
TABLE_STOCK_PRICE = 'StockPrice'
TABLE_STOCK_DATA_BARCHART = 'StockDataBarchart'

#Views
VIEW_OPTION_DATA = 'OptionData'
VIEW_FUNDAMENTAL_DATA = 'FundamentalData'
 
 # Dividend Radar
URL_DIVIDEND_RADAR = "https://www.portfolio-insight.com/dividend-radar"

# App Logfile
PATH_APP_LOGFILE = BASE_DIR / 'app.log'

# Symbols excel file
PATH_SYMBOLS_EXCHANGE_FILE = BASE_DIR / 'symbols_exchange.xlsx'

#Google Upload Config
PATH_ON_GOOGLE_DRIVE = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"
FILENAME_GOOGLE_DRIVE = FILENAME_MERGED_DATAFRAME
PATH_FOR_SERVICE_ACCOUNT_FILE = "service_account.json"

# Symbols and exchange
df =pd.read_excel(PATH_SYMBOLS_EXCHANGE_FILE)
SYMBOLS_EXCHANGE = dict(zip(df['symbol'], df['exchange']))

SYMBOLS = list(SYMBOLS_EXCHANGE.keys())

# monte_carlo_simulator
RANDOM_SEED=42
IV_CORECTION='auto'
RISK_FREE_RATE = 0.03
NUM_SIMULATIONS = 100000
TRANSACTION_COST_PER_CONTRACT = 3.5 # in USD

# =============================================================================
# SIMPLIFIED DATA COLLECTION CONFIGURATION
# =============================================================================

# Symbol selection
SYMBOL_SELECTION = {
    "mode": "max",                   # "all", "list", "file", "max"
    "symbols": [""],             # Used when mode="list"
    "file_path": None,               # Used when mode="file"
    "max_symbols": 21,               # Used when mode="max" or as limit for "all"
    "use_max_limit": False            # If True, applies max_symbols limit to any mode
}

# =============================================================================
# OPTIONS COLLECTION RULES (processed in order)
# =============================================================================
OPTIONS_COLLECTION_RULES = [
    {
        "name": "weekly_short_term",
        "enabled": True,
        "days_range": [1, 40],            # Today + 1 to 60 days
        "frequency": "every_friday",      # "every_friday", "monthly_3rd_friday", "quarterly_3rd_friday"
        "description": "Weekly options for next 2 months"
    },
    {
        "name": "monthly_medium_term", 
        "enabled": True,
        "days_range": [61, 120],
        "frequency": "monthly_3rd_friday",
        "description": "Monthly options 2-6 months out"
    },
    {
        "name": "leaps_long_term",
        "enabled": True,                 # Disabled by default
        "days_range": [180, 500],         # Current married put range
        "frequency": "monthly_3rd_friday",      # Changed from monthly_3rd_friday to every_friday
        "description": "LEAPS options for married put strategies"
    }
]

# =============================================================================

