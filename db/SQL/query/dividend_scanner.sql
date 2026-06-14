SELECT
	SYMBOL,
	"Summary_dividendYield" AS DIVIDEND_YIELD,
	"Summary_payoutRatio" AS PAYOUT_RATIO,
	"FreeCashFlow" AS FREE_CASHFLOW,
	"OperatingCashFlow" AS OPERATING_CASHFLOW,
	"MarketCap" AS MARKET_CAP,
	"FinData_debtToEquity" AS DEBT_TO_EQUITY,
	"FinData_currentRatio" AS CURRENT_RATIO,
	"Summary_trailingPE" AS TRAILING_PE,
	"KeyStats_priceToBook" AS PRICE_TO_BOOK,
	"Summary_beta" AS BETA,
	"Summary_priceToSalesTrailing12Months" AS PRICE_TO_SALES,
	"KeyStats_enterpriseToEbitda" AS EV_EBITDA,
	"Summary_fiveYearAvgDividendYield" AS AVG_YIELD_5Y,
	"FinData_returnOnEquity" AS ROE,
	"FinData_returnOnAssets" AS ROA,
	"FinData_profitMargins" AS PROFIT_MARGIN,
	"FinData_earningsGrowth" AS EARNINGS_GROWTH,
	"FinData_revenueGrowth" AS REVENUE_GROWTH,
	LIVE_STOCK_PRICE AS CURRENT_PRICE,
	"RSI_14" AS RSI,
	"SMA_200" AS SMA_200,
	"SMA_50" AS SMA_50,
	"STOCHk_14_3_1" AS STOCH_K,
	"STOCHd_14_3_1" AS STOCH_D,
	"MACD_12_26_9" AS MACD,
	"MACDs_12_26_9" AS MACD_SIGNAL,
	"BBL_20_2.0_2.0" AS BB_LOWER,
	"BBU_20_2.0_2.0" AS BB_UPPER,
	IV AS CURRENT_IV,
	IV_LOW AS IV_MIN_52W,
	IV_HIGH AS IV_MAX_52W,
	COMPANY_NAME AS NAME,
	COMPANY_SECTOR AS SECTOR,
	COMPANY_INDUSTRY AS INDUSTRY
FROM
	"StockData"
WHERE
	"Summary_dividendYield" IS NOT NULL
ORDER BY
	SYMBOL DESC