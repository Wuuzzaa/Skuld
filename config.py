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
PATH_DATAFRAME_YAHOOQUERY_FINANCIAL_PROCESSED_FEATHER = PATH_DATA / 'yahooquery_financial_processed.feather'
PATH_DATAFRAME_LIVE_STOCK_PRICES_FEATHER = PATH_DATA / 'live_stock_prices.feather'

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
    #"open",
    #"high",
    #"low",
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
    #"Price",
    "Div-Yield",
    "5Y-Avg-Yield",
    "Current-Div",
 #   "Payouts/Year",
    "Annualized",
    "Previous-Div",
    "Ex-Date",
 #   "Pay-Date",
    #"Low",
    #"High",
    #"DGR-1Y",
    #"DGR-3Y",
    #"DGR-5Y",
    #"DGR-10Y",
    "TTR-1Y",
    "TTR-3Y",
    "Fair-Value",
    #"FV-%",
    #"Streak-Basis",
    "Chowder-Number",
    "EPS-1Y",
    "Revenue-1Y",
    "NPM",
    "CF/Share",
    #"ROE",
    #"Current-R",
    #"Debt/Capital",
    #"ROTC",
    #"P/E",
    #"P/BV",
    #"PEG",
    "Industry",
    ##################
    # Fundamentals
    ##################
    "MarketCap",
    "EnterpriseValue", 
    "TotalRevenue",
    "TotalAssets",
    "NetIncome",
    "EBITDA",
    #"FreeCashFlow",
    #"OperatingCashFlow",
    #"StockholdersEquity",
    "TotalDebt",
    "CurrentAssets",
    "Yahoo_DividendYield",
    #"CurrentLiabilities",
    #"TangibleBookValue",
    #"OrdinarySharesNumber", 
    #"BasicEPS",
    #"DilutedEPS",
    #"CashDividendsPaid",
    #"PE_Ratio",
    #"PB_Ratio", 
    #"DebtEquity_Ratio",
    #"ROE_Fund",
    "ROA",
  #  "DividendYield_Calc",

    ################## 
    # Live Stock Price Columns (added during data collection)
    ##################
    "live_stock_price",
    #"live_price_timestamp", 
    #"live_price_available", 
    #"current_stock_price"  # Unified price column (live or fallback)

    ##################
    # Option Pricing Columns (calculated during merge for ALL options)
    ##################
    "IntrinsicValue",      # Calls: max(stock - strike, 0) | Puts: max(strike - stock, 0)
    "ExtrinsicValue",      # max(theoPrice - IntrinsicValue, 0) for all options

    ##################
    # Dividend Stability Analysis (for Married Put strategies)
    ##################
    #"dividend_stability_label",        # "STABLE", "OK_CHECK_REQUIRED", "NOT_STABLE"
    #"dividend_stability_score",        # 0-7 score
    #"dividend_regularity_ratio",       # % years with payments
    #"median_payments_per_year",        # Payment frequency (numeric)
    "dividend_frequency_type",         # "Quarterly", "Semi-annual", "Annual", "Irregular"
    "dividend_frequency_consistency",  # 0-1 consistency score
    #"dividend_cuts_count",             # Number of YoY cuts
    "dividend_streak_years",           # Years without cuts
    #"dividend_cagr",                   # 10-year Compound Annual Growth Rate (CAGR) of dividends
    #"dividend_volatility",             # Volatility measure
    #"payout_ratio_stable",            # % years with sustainable payout
    #"fcf_coverage_adequate",          # FCF coverage quality
    #"earnings_coverage",              # Earnings coverage ratio
    #"analysis_notes"                  # Detailed reasoning
]

# JMS Settings
JMS_TP_GOAL = 0.6
JMS_MENTAL_STOP = 2


# =============================================================================
# SIMPLIFIED DATA COLLECTION CONFIGURATION
# =============================================================================


# Symbol selection
SYMBOL_SELECTION = {
    "mode": "list",                   # "all", "list", "file", "max"
    "symbols": ["AAPL"],             # Used when mode="list"
    "file_path": None,               # Used when mode="file"
    "max_symbols": 10,               # Used when mode="max" or as limit for "all"
    "use_max_limit": False            # If True, applies max_symbols limit to any mode
}

# =============================================================================
# OPTIONS COLLECTION RULES (processed in order)
# =============================================================================
OPTIONS_COLLECTION_RULES = [
    {
        "name": "weekly_short_term",
        "enabled": True,
        "days_range": [1, 60],            # Today + 1 to 60 days
        "frequency": "every_friday",      # "every_friday", "monthly_3rd_friday", "quarterly_3rd_friday"
        "description": "Weekly options for next 2 months"
    },
    {
        "name": "monthly_medium_term", 
        "enabled": False,
        "days_range": [61, 180],
        "frequency": "monthly_3rd_friday",
        "description": "Monthly options 2-6 months out"
    },
    {
        "name": "leaps_long_term",
        "enabled": False,                 # Disabled by default
        "days_range": [180, 365],         # Current married put range
        "frequency": "every_friday",      # Changed from monthly_3rd_friday to every_friday
        "description": "LEAPS options for married put strategies"
    }
]

# =============================================================================




