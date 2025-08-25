import pandas as pd
from pathlib import Path

# Base path relative to base folder
BASE_DIR = Path(__file__).resolve().parent

# Filename merged dataframe the final file for the streamlit app
FILENAME_MERGED_DATAFRAME = 'merged_df.feather'

# Data folder
PATH_DATA = BASE_DIR / 'data'
PATH_OPTION_DATA_TRADINGVIEW = PATH_DATA / 'json' / 'option_data_tradingview'
PATH_DATAFRAME_OPTION_DATA_FEATHER = PATH_DATA / 'option_data.feather'
PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER = PATH_DATA / 'price_and_indicators.feather'
PATH_DATAFRAME_DATA_MERGED_FEATHER = PATH_DATA / FILENAME_MERGED_DATAFRAME
PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER = PATH_DATA / 'price_target_df.feather'
PATH_DATAFRAME_EARNING_DATES_FEATHER = PATH_DATA / 'earning_dates.feather'
PATH_DATAFRAME_YAHOOQUERY_OPTION_CHAIN_FEATHER = PATH_DATA / 'yahooquery_option_chain.feather'
PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_FEATHER = PATH_DATA / 'yahooquery_financial.feather'

# Dividend Radar
URL_DIVIDEND_RADAR = "https://www.portfolio-insight.com/dividend-radar"
PATH_DIVIDEND_RADAR = PATH_DATA / 'dividend_radar.feather'

# App Logfile
PATH_APP_LOGFILE = BASE_DIR / 'app.log'

# Symbols excel file
PATH_SYMBOLS_EXCHANGE_FILE = BASE_DIR / 'symbols_exchange.xlsx'

#Google Upload Config
PATH_ON_GOOGLE_DRIVE = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"
FILENAME_GOOGLE_DRIVE = FILENAME_MERGED_DATAFRAME
#PATH_FOR_SERVICE_ACCOUNT_FILE = "service_account.json"

PATH_FOR_SERVICE_ACCOUNT_FILE = r'C:\Python\google_upload2\service_account.json' 

# FOLDERPATHS relative to main.py
FOLDERPATHS = \
    [
        PATH_DATA,
        PATH_OPTION_DATA_TRADINGVIEW
    ]

# Symbols and exchange
df =pd.read_excel(PATH_SYMBOLS_EXCHANGE_FILE)
SYMBOLS_EXCHANGE = dict(zip(df['symbol'], df['exchange']))

SYMBOLS = list(SYMBOLS_EXCHANGE.keys())

# set the columns needed for further work
DATAFRAME_DATA_MERGED_COLUMNS = [
    "symbol",
    "expiration_date",
    "option-type",
    "strike",
    "recommendation",
    "Recommend.Other",
    "Recommend.All",
    "Recommend.MA",
    "ask",
    "bid",
    "delta",
    "gamma",
    "iv",
    "rho",
    "theoPrice",
    "theta",
    "vega",
    "option",
    "time",
    "exchange",
    "volume",
    "open",
    "high",
    "low",
    "close",
    "change",
    "analyst_mean_target",
    # "recommendation_buy_amount",
    # "recommendation_neutral_amount",
    # "recommendation_sell_amount",
    "RSI",
    # "RSI[1]",
    "Stoch.K",
    # "Stoch.D",
    # "Stoch.K[1]",
    # "Stoch.D[1]",
    # "CCI20",
    # "CCI20[1]",
    "ADX",
    # "ADX+DI",
    # "ADX-DI",
    # "ADX+DI[1]",
    # "ADX-DI[1]",
    # "AO",
    # "AO[1]",
    # "Mom",
    # "Mom[1]",
    "MACD.macd",
    #"MACD.signal",
    # "Rec.Stoch.RSI",
    # "Stoch.RSI.K",
    # "Rec.WR",
    # "W.R",
    # "Rec.BBPower",
    # "BBPower",
    # "Rec.UO",
    # "UO",
    # "EMA5",
    # "SMA5",
    # "EMA10",
    # "SMA10",
    # "EMA20",
    # "SMA20",
    # "EMA30",
    # "SMA30",
    # "EMA50",
    # "SMA50",
    # "EMA100",
    # "SMA100",
    # "EMA200",
    # "SMA200",
    # "Rec.Ichimoku",
    # "Ichimoku.BLine",
    # "Rec.VWMA",
    "VWMA",
    # "Rec.HullMA9",
    # "HullMA9",
    # "Pivot.M.Classic.S3",
    # "Pivot.M.Classic.S2",
    # "Pivot.M.Classic.S1",
    # "Pivot.M.Classic.Middle",
    # "Pivot.M.Classic.R1",
    # "Pivot.M.Classic.R2",
    # "Pivot.M.Classic.R3",
    # "Pivot.M.Fibonacci.S3",
    # "Pivot.M.Fibonacci.S2",
    # "Pivot.M.Fibonacci.S1",
    # "Pivot.M.Fibonacci.Middle",
    # "Pivot.M.Fibonacci.R1",
    # "Pivot.M.Fibonacci.R2",
    # "Pivot.M.Fibonacci.R3",
    # "Pivot.M.Camarilla.S3",
    # "Pivot.M.Camarilla.S2",
    # "Pivot.M.Camarilla.S1",
    # "Pivot.M.Camarilla.Middle",
    # "Pivot.M.Camarilla.R1",
    # "Pivot.M.Camarilla.R2",
    # "Pivot.M.Camarilla.R3",
    # "Pivot.M.Woodie.S3",
    # "Pivot.M.Woodie.S2",
    # "Pivot.M.Woodie.S1",
    # "Pivot.M.Woodie.Middle",
    # "Pivot.M.Woodie.R1",
    # "Pivot.M.Woodie.R2",
    # "Pivot.M.Woodie.R3",
    # "Pivot.M.Demark.S1",
    # "Pivot.M.Demark.Middle",
    # "Pivot.M.Demark.R1",
    # "P.SAR",
    "BB.lower",
    "BB.upper",
    # "AO[2]",
    "earnings_date",
    'option_volume',
    'option_open_interest',

    ##################
    #Dividend Radar ,
    ##################
    "Company",
    "FV",
    "Sector",
    "No-Years",
    "Price",
    "Div-Yield",
    "5Y-Avg-Yield",
    "Current-Div",
 #   "Payouts/Year",
    "Annualized",
    "Previous-Div",
    "Ex-Date",
    "Pay-Date",
    "Low",
    "High",
    "DGR-1Y",
    "DGR-3Y",
    "DGR-5Y",
    "DGR-10Y",
    "TTR-1Y",
    "TTR-3Y",
    "Fair-Value",
    "FV-%",
    "Streak-Basis",
    "Chowder-Number",
    "EPS-1Y",
    "Revenue-1Y",
    "NPM",
    "CF/Share",
    "ROE",
    "Current-R",
    "Debt/Capital",
    "ROTC",
    "P/E",
    "P/BV",
    "PEG",
    "Industry",
]

# JMS Settings
JMS_TP_GOAL = 0.6
JMS_MENTAL_STOP = 2


# =============================================================================
# DATA COLLECTION CONFIGURATION - HIERARCHICAL PRIORITY SYSTEM
# =============================================================================

"""
DATA COLLECTION PRIORITY HIERARCHY (higher priority overrides lower):

1. GENERAL_TEST_MODE (highest priority)
   - Overrides ALL other settings when enabled
   - Collects only first 5 symbols × first 3 expiry dates
   - For development and debugging

2. MARRIED_PUT_TEST_MODE (medium priority) 
   - Overrides standard options when enabled
   - Collects ALL symbols but only specific LEAPS range
   - For married put strategy development
   - Cannot run together with GENERAL_TEST_MODE

3. EXTENDED_LEAPS_MODE (medium priority)
   - Overrides BASIC_LEAPS when enabled
   - Collects standard options + all third Fridays in range
   - For comprehensive LEAPS analysis

4. BASIC_LEAPS_MODE (low priority)
   - Default behavior when no test modes active
   - Collects standard options + first third Friday after target days
   - Standard production mode

5. STANDARD_OPTIONS_ONLY (lowest priority)
   - Baseline: weekly + monthly options only
   - Always included unless overridden by test modes
"""

# =============================================================================
# 1. GENERAL TEST MODE (HIGHEST PRIORITY - OVERRIDES ALL)
# =============================================================================
GENERAL_TEST_MODE_ENABLED = False          # Master override for development
GENERAL_TEST_MODE_MAX_SYMBOLS = 7          # Limit symbols in test mode
GENERAL_TEST_MODE_MAX_EXPIRY_DATES = 3     # Limit expiry dates in test mode

# =============================================================================
# 2. MARRIED PUT TEST MODE (MEDIUM PRIORITY - LEAPS ONLY)
# =============================================================================
MARRIED_PUT_TEST_MODE_ENABLED = True      # Test mode for married put development
MARRIED_PUT_TEST_MODE_MAX_SYMBOLS = 4     # Limit symbols in married put test mode (set to None for all symbols)
MARRIED_PUT_TEST_MODE_MIN_DAYS = 120       # Only collect options after this many days
MARRIED_PUT_TEST_MODE_MAX_DAYS = 250       # Only collect options before this many days
# Note: Collects limited/all symbols but only LEAPS in specified range

# =============================================================================
# 3. EXTENDED LEAPS MODE (MEDIUM PRIORITY - OVERRIDES BASIC LEAPS)
# =============================================================================
MARRIED_PUT_EXTENDED_LEAPS_ENABLED = False # Collect ALL third Fridays in range
MARRIED_PUT_EXTENDED_LEAPS_MIN_DAYS = 90   # Minimum days for extended LEAPS
MARRIED_PUT_EXTENDED_LEAPS_MAX_DAYS = 270  # Maximum days for extended LEAPS

# =============================================================================
# 4. BASIC LEAPS MODE (LOW PRIORITY - DEFAULT PRODUCTION)
# =============================================================================
MARRIED_PUT_BASIC_LEAPS_ENABLED = True     # Basic LEAPS collection
MARRIED_PUT_BASIC_LEAPS_TARGET_DAYS = [180, 360]  # First third Friday after these days

# =============================================================================
# 5. STANDARD OPTIONS (LOWEST PRIORITY - ALWAYS INCLUDED UNLESS OVERRIDDEN)
# =============================================================================
STANDARD_WEEKLY_OPTIONS_DAYS = 60          # Every Friday for next N days
STANDARD_MONTHLY_OPTIONS_MONTHS = 4        # Third Friday of next N months

# =============================================================================




