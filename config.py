from pathlib import Path

SYMBOLS_EXCHANGE = {
    "AAPL": 'NASDAQ',
    "AMD": 'NASDAQ',
    "AMZN": 'NASDAQ',
    "AVGO": 'NASDAQ',
    "BA": 'NYSE',
    "BABA": 'NYSE',
    "BIDU": 'NASDAQ',
    "C": 'NYSE',
    "CAT": 'NYSE',
    "COF": 'NYSE',
    "COST": 'NASDAQ',
    "CRM": 'NYSE',
    "CRWD": 'NASDAQ',
    "CSCO": 'NASDAQ',
    "DIA": 'AMEX',
    "DIS": 'NYSE',
    "EEM": 'AMEX',
    "GE": 'NYSE',
    "GLD": 'AMEX',
    "GM": 'NYSE',
    "GOOG": 'NASDAQ',
    "GS": 'NYSE',
    "HD": 'NYSE',
    "IBM": 'NYSE',
    "IWM": 'AMEX',
    "JPM": 'NYSE',
    "LOW": 'NYSE',
    "MCD": 'NYSE',
    "META": 'NASDAQ',
    "MMM": 'NYSE',
    "MRVL": 'NASDAQ',
    "MSFT": 'NASDAQ',
    "MU": 'NASDAQ',
    "NFLX": 'NASDAQ',
    "NVDA": 'NASDAQ',
    "ORCL": 'NYSE',
    "PG": 'NYSE',
    "QCOM": 'NASDAQ',
    "QQQ": 'NASDAQ',
    "SBUX": 'NASDAQ',
    "SHOP": 'NYSE',
    "SMH": 'NASDAQ',
    "SPY": 'AMEX',
    "SQ": 'NYSE',
    "TGT": 'NYSE',
    "TLT": 'NASDAQ',
    "TSLA": 'NASDAQ',
    "UBER": 'NYSE',
    "USO": 'AMEX',
    "V": 'NYSE',
    "WFC": 'NYSE',
    "WMT": 'NYSE',
    "X": 'NYSE',
    "XBI": 'AMEX',
    "XLU": 'AMEX',
    "XOM": 'NYSE',
    "XOP": 'AMEX',
}

SYMBOLS = list(SYMBOLS_EXCHANGE.keys())

# Basisverzeichnis relativ zur main.py oder der config.py
BASE_DIR = Path(__file__).resolve().parent

# Datenverzeichnis
PATH_DATA = BASE_DIR / 'data'
PATH_OPTION_DATA_TRADINGVIEW = PATH_DATA / 'json' / 'option_data_tradingview'
PATH_DATAFRAME_OPTION_DATA_FEATHER = PATH_DATA / 'option_data.feather'
PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER = PATH_DATA / 'price_and_indicators.feather'
PATH_DATAFRAME_DATA_MERGED_FEATHER = PATH_DATA / 'merged_df.feather'
PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_FEATHER = PATH_DATA / 'price_target_df.feather'

#Dividend Radar
URL_DIVIDEND_RADAR = "https://www.portfolio-insight.com/dividend-radar"
PATH_DIVIDEND_RADAR = PATH_DATA / 'dividend_radar.feather'

# App Logfile
PATH_APP_LOGFILE = BASE_DIR / 'app.log'

#Google Upload Config

PATH_ON_GOOGLE_DRIVE = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"
FILENAME_GOOGLE_DRIVE = "merged_data.feather"
PATH_FOR_SERVICE_ACCOUNT_FILE = "service_account.json"

# FOLDERPATHS relative to main.py
FOLDERPATHS = \
    [
        PATH_DATA,
        PATH_OPTION_DATA_TRADINGVIEW
    ]

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




