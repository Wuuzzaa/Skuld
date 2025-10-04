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
 
# Database
PATH_DATABASE = BASE_DIR / 'db/financial_data.db'
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
#Views
VIEW_OPTION_DATA = 'OptionData'
VIEW_FUNDAMENTAL_DATA = 'FundamentalData'
 
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

PATH_FOR_SERVICE_ACCOUNT_FILE = r'C:\Python\SKULD\service_account.json' 

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
    # Fundamentals - ALLE 286 verfügbaren Spalten (nur wichtigste eingeblendet)
    ##################
    
    # === CORE DISPLAY COLUMNS (aktuell sichtbar) ===
    "MarketCap",
    "TotalRevenue", 
    "NetIncome",
    "EBITDA",
    #"Yahoo_DividendYield",  # Will be mapped from Summary_dividendYield
    #"ROA",  # Available as FinData_returnOnAssets
    
    # === META COLUMNS ===
    #"symbol",  # Always included automatically
    #"asOfDate",
    #"periodType", 
    #"currencyCode",
    
    # === FINANCIAL STATEMENTS - Balance Sheet ===
    #"AccountsPayable",
    #"AccountsReceivable", 
    #"AccumulatedDepreciation",
    #"AvailableForSaleSecurities",
    #"CapitalStock",
    #"CashAndCashEquivalents",
    #"CashCashEquivalentsAndShortTermInvestments",
    #"CashEquivalents",
    #"CashFinancial",
    #"CommercialPaper",
    #"CommonStock",
    #"CommonStockEquity",
    #"CurrentAssets",
    #"CurrentDebt",
    #"CurrentDebtAndCapitalLeaseObligation",
    #"CurrentDeferredLiabilities",
    #"CurrentDeferredRevenue", 
    #"CurrentLiabilities",
    #"DeferredIncomeTax",
    #"DeferredTax",
    #"GrossPPE",
    #"IncomeTaxPayable",
    #"Inventory",
    #"InvestedCapital",
    #"InvestmentinFinancialAssets",
    #"InvestmentsAndAdvances",
    #"LandAndImprovements",
    #"Leases",
    #"LongTermDebt",
    #"LongTermDebtAndCapitalLeaseObligation",
    #"MachineryFurnitureEquipment",
    #"NetDebt",
    #"NetPPE",
    #"NetTangibleAssets",
    #"NonCurrentDeferredAssets",
    #"NonCurrentDeferredTaxesAssets",
    #"OrdinarySharesNumber",
    #"OtherCurrentAssets",
    #"OtherCurrentBorrowings",
    #"OtherCurrentLiabilities",
    #"OtherInvestments",
    #"OtherNonCurrentAssets",
    #"OtherNonCurrentLiabilities",
    #"OtherProperties",
    #"OtherReceivables",
    #"OtherShortTermInvestments",
    #"Payables",
    #"PayablesAndAccruedExpenses",
    #"Properties",
    #"Receivables",
    #"RetainedEarnings",
    #"ShareIssued",
    #"StockholdersEquity",
    #"TangibleBookValue",
    #"TotalAssets",
    #"TotalCapitalization",
    #"TotalDebt",
    #"TotalEquityGrossMinorityInterest",
    #"TotalLiabilitiesNetMinorityInterest",
    #"TotalNonCurrentAssets",
    #"TotalNonCurrentLiabilitiesNetMinorityInterest",
    #"TotalTaxPayable",
    #"TradeandOtherPayablesNonCurrent",
    #"TreasurySharesNumber",
    #"WorkingCapital",
    
    # === FINANCIAL STATEMENTS - Income Statement ===
    #"BasicAverageShares",
    #"BasicEPS",
    #"CostOfRevenue",
    #"DilutedAverageShares", 
    #"DilutedEPS",
    #"DilutedNIAvailtoComStockholders",
    #"EBIT",
    #"EnterpriseValue",
    #"EnterprisesValueEBITDARatio",
    #"EnterprisesValueRevenueRatio",
    #"FreeCashFlow",
    #"GainsLossesNotAffectingRetainedEarnings",
    #"GrossProfit",
    #"InterestExpense",
    #"InterestExpenseNonOperating",
    #"InterestIncome", 
    #"InterestIncomeNonOperating",
    #"NetIncomeCommonStockholders",
    #"NetIncomeContinuousOperations",
    #"NetIncomeFromContinuingAndDiscontinuedOperation",
    #"NetIncomeFromContinuingOperationNetMinorityInterest",
    #"NetIncomeFromContinuingOperations",
    #"NetIncomeIncludingNoncontrollingInterests",
    #"NetInterestIncome",
    #"NetNonOperatingInterestIncomeExpense",
    #"NormalizedEBITDA",
    #"NormalizedIncome",
    #"OperatingExpense",
    #"OperatingIncome",
    #"OperatingRevenue",
    #"OtherIncomeExpense",
    #"OtherNonOperatingIncomeExpenses",
    #"PretaxIncome",
    #"ReconciledCostOfRevenue",
    #"ReconciledDepreciation",
    #"ResearchAndDevelopment",
    #"SellingGeneralAndAdministration",
    #"StockBasedCompensation",
    #"TaxEffectOfUnusualItems",
    #"TaxProvision",
    #"TaxRateForCalcs",
    #"TotalExpenses",
    #"TotalOperatingIncomeAsReported",
    
    # === FINANCIAL STATEMENTS - Cash Flow ===
    #"BeginningCashPosition",
    #"CapitalExpenditure",
    #"CapitalLeaseObligations",
    #"CashDividendsPaid",
    #"CashFlowFromContinuingFinancingActivities",
    #"CashFlowFromContinuingInvestingActivities", 
    #"CashFlowFromContinuingOperatingActivities",
    #"ChangeInAccountPayable",
    #"ChangeInCashSupplementalAsReported",
    #"ChangeInInventory",
    #"ChangeInOtherCurrentAssets",
    #"ChangeInOtherCurrentLiabilities",
    #"ChangeInOtherWorkingCapital",
    #"ChangeInPayable",
    #"ChangeInPayablesAndAccruedExpense",
    #"ChangeInReceivables",
    #"ChangeInWorkingCapital",
    #"ChangesInAccountReceivables",
    #"ChangesInCash",
    #"CommonStockDividendPaid",
    #"CommonStockIssuance",
    #"CommonStockPayments",
    #"CurrentCapitalLeaseObligation",
    #"DepreciationAmortizationDepletion",
    #"DepreciationAndAmortization",
    #"EndCashPosition",
    #"FinancingCashFlow",
    #"IncomeTaxPaidSupplementalData",
    #"InterestPaidSupplementalData",
    #"InvestingCashFlow",
    #"IssuanceOfCapitalStock",
    #"IssuanceOfDebt",
    #"LongTermCapitalLeaseObligation",
    #"LongTermDebtIssuance",
    #"LongTermDebtPayments",
    #"NetBusinessPurchaseAndSale",
    #"NetCommonStockIssuance",
    #"NetInvestmentPurchaseAndSale",
    #"NetIssuancePaymentsOfDebt",
    #"NetLongTermDebtIssuance",
    #"NetOtherFinancingCharges",
    #"NetOtherInvestingChanges",
    #"NetPPEPurchaseAndSale",
    #"NetShortTermDebtIssuance",
    #"OperatingCashFlow",
    #"OtherEquityAdjustments",
    #"OtherNonCashItems",
    #"PurchaseOfBusiness",
    #"PurchaseOfInvestment",
    #"PurchaseOfPPE",
    #"RepaymentOfDebt",
    #"RepurchaseOfCapitalStock",
    #"SaleOfInvestment",
    
    # === KEY STATS (KeyStats_ prefix) ===
    #"KeyStats_maxAge",
    #"KeyStats_priceHint",
    #"KeyStats_enterpriseValue",
    #"KeyStats_forwardPE",
    #"KeyStats_profitMargins",
    #"KeyStats_floatShares",
    #"KeyStats_sharesOutstanding",
    #"KeyStats_sharesShort",
    #"KeyStats_sharesShortPriorMonth",
    #"KeyStats_sharesShortPreviousMonthDate",
    #"KeyStats_dateShortInterest",
    #"KeyStats_sharesPercentSharesOut",
    #"KeyStats_heldPercentInsiders",
    #"KeyStats_heldPercentInstitutions",
    #"KeyStats_shortRatio",
    #"KeyStats_shortPercentOfFloat",
    #"KeyStats_beta",
    #"KeyStats_impliedSharesOutstanding",
    #"KeyStats_category",
    #"KeyStats_bookValue",
    #"KeyStats_priceToBook",
    #"KeyStats_fundFamily",
    #"KeyStats_legalType",
    #"KeyStats_lastFiscalYearEnd",
    #"KeyStats_nextFiscalYearEnd",
    #"KeyStats_mostRecentQuarter",
    #"KeyStats_earningsQuarterlyGrowth",
    #"KeyStats_netIncomeToCommon",
    #"KeyStats_trailingEps",
    #"KeyStats_forwardEps",
    #"KeyStats_lastSplitFactor",
    #"KeyStats_lastSplitDate",
    #"KeyStats_enterpriseToRevenue",
    #"KeyStats_enterpriseToEbitda",
    #"KeyStats_52WeekChange",
    #"KeyStats_SandP52WeekChange",
    #"KeyStats_lastDividendValue",
    #"KeyStats_lastDividendDate",
    #"KeyStats_latestShareClass", 
    #"KeyStats_leadInvestor",
    
    # === EPS GROWTH (Custom Calculated) ===
    "Forward_EPS_Growth_Percent",  # Main screening metric
    
    # === SUMMARY DETAIL (Summary_ prefix) ===
    #"Summary_maxAge",
    #"Summary_priceHint",
    #"Summary_previousClose",
    #"Summary_open",
    #"Summary_dayLow",
    #"Summary_dayHigh",
    #"Summary_regularMarketPreviousClose",
    #"Summary_regularMarketOpen",
    #"Summary_regularMarketDayLow",
    #"Summary_regularMarketDayHigh",
    #"Summary_dividendRate",
    #"Summary_dividendYield",  # Maps to Yahoo_DividendYield
    #"Summary_exDividendDate",
    #"Summary_payoutRatio",
    #"Summary_fiveYearAvgDividendYield",
    #"Summary_beta",
    #"Summary_trailingPE",
    #"Summary_forwardPE",
    #"Summary_volume",
    #"Summary_regularMarketVolume",
    #"Summary_averageVolume",
    #"Summary_averageVolume10days",
    #"Summary_averageDailyVolume10Day",
    #"Summary_bid",
    #"Summary_ask",
    #"Summary_bidSize",
    #"Summary_askSize",
    #"Summary_marketCap",
    #"Summary_fiftyTwoWeekLow",
    #"Summary_fiftyTwoWeekHigh",
    #"Summary_priceToSalesTrailing12Months",
    #"Summary_fiftyDayAverage",
    #"Summary_twoHundredDayAverage",
    #"Summary_trailingAnnualDividendRate",
    #"Summary_trailingAnnualDividendYield",
    #"Summary_currency",
    #"Summary_fromCurrency",
    #"Summary_toCurrency",
    #"Summary_lastMarket",
    #"Summary_coinMarketCapLink",
    #"Summary_algorithm",
    #"Summary_tradeable",
    
    # === FINANCIAL DATA (FinData_ prefix) ===
    #"FinData_maxAge",
    #"FinData_currentPrice",
    #"FinData_targetHighPrice",
    #"FinData_targetLowPrice",
    #"FinData_targetMeanPrice",
    #"FinData_targetMedianPrice",
    #"FinData_recommendationMean",
    #"FinData_recommendationKey",
    #"FinData_numberOfAnalystOpinions",
    #"FinData_totalCash",
    #"FinData_totalCashPerShare",
    #"FinData_ebitda",
    #"FinData_totalDebt",
    #"FinData_quickRatio",
    #"FinData_currentRatio",
    #"FinData_totalRevenue",
    #"FinData_debtToEquity",
    #"FinData_revenuePerShare",
    #"FinData_returnOnAssets",  # Maps to ROA
    #"FinData_returnOnEquity",
    #"FinData_grossProfits",
    #"FinData_freeCashflow",
    #"FinData_operatingCashflow",
    #"FinData_earningsGrowth",      # Alternative EPS Growth
    #"FinData_revenueGrowth", 
    #"FinData_grossMargins",
    #"FinData_ebitdaMargins",
    #"FinData_operatingMargins",
    #"FinData_profitMargins",
    #"FinData_financialCurrency",
    
    # === CALCULATED RATIOS (from prepare_fundamentals_for_merge_v2) ===
    #"PE_Ratio_Calc",
    #"PS_Ratio",
    #"DebtToMarketCap",
    #"EV_EBITDA_Approx",

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
    "ExtrinsicValue"     # max(theoPrice - IntrinsicValue, 0) for all options

]


# JMS Settings
JMS_TP_GOAL = 0.6
JMS_MENTAL_STOP = 2

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
    "mode": "all",                   # "all", "list", "file", "max"
    "symbols": ["AAPL","MO"],             # Used when mode="list"
    "file_path": None,               # Used when mode="file"
    "max_symbols": 1000,               # Used when mode="max" or as limit for "all"
    "use_max_limit": True            # If True, applies max_symbols limit to any mode
}

# =============================================================================
# OPTIONS COLLECTION RULES (processed in order)
# =============================================================================
OPTIONS_COLLECTION_RULES = [
    {
        "name": "weekly_short_term",
        "enabled": False,
        "days_range": [1, 40],            # Today + 1 to 60 days
        "frequency": "every_friday",      # "every_friday", "monthly_3rd_friday", "quarterly_3rd_friday"
        "description": "Weekly options for next 2 months"
    },
    {
        "name": "monthly_medium_term", 
        "enabled": False,
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