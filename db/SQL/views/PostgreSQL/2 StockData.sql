DROP VIEW IF EXISTS "StockData" CASCADE;

CREATE VIEW
    "StockData" AS
SELECT
	A.SYMBOL,
	A.close as LIVE_STOCK_PRICE,
	B.EARNINGS_DATE,
	CAST(B.EARNINGS_DATE::DATE - CURRENT_DATE AS INTEGER) AS days_to_earnings,
	C.ANALYST_MEAN_TARGET,

	-- StockImpliedVolatilityMassive
    d.iv,
    d.iv_low,
    d.iv_high,
    d.iv_rank,
    d.iv_percentile,
	-- days of options data available
	CAST(CURRENT_DATE - g.from_date AS INTEGER) AS days_of_options_data_history,

	-- StockVolatility
	e.historical_volatility_30d,

	-- DividendData
	f.dividend_growth_years,
	f.dividend_classification,
	f.LAST_DIVIDEND,
    f.LAST_DIVIDEND_DATE,
	f.NO_DIVIDEND_PAYOUTS_LAST_YEAR,
	CAST(CURRENT_DATE - h.from_date AS INTEGER) AS days_of_stock_prices_history
FROM
	"StockPricesYahoo" AS A
	LEFT OUTER JOIN (
		SELECT
			SYMBOL,
			CASE
				WHEN EARNINGS_DATE LIKE '%.%.%' THEN SUBSTR(EARNINGS_DATE, 7, 4) || '-' || SUBSTR(EARNINGS_DATE, 4, 2) || '-' || SUBSTR(EARNINGS_DATE, 1, 2)
				ELSE NULL
			END AS EARNINGS_DATE
		FROM
			"EarningDates"
	) AS B ON A.SYMBOL = B.SYMBOL
	LEFT OUTER JOIN "AnalystPriceTargets" AS C ON A.SYMBOL = C.SYMBOL
	LEFT OUTER JOIN "StockImpliedVolatilityMassive" AS d ON a.symbol = d.symbol
	LEFT OUTER JOIN "StockVolatility" AS E ON A.SYMBOL = E.SYMBOL
	LEFT OUTER JOIN "DividendData" AS F ON A.SYMBOL = F.SYMBOL
	LEFT OUTER JOIN (
		SELECT symbol, MIN(from_date) AS from_date FROM "OptionDataMassiveMasterData" GROUP BY symbol
	) AS G ON A.SYMBOL = G.SYMBOL
	LEFT OUTER JOIN (
		SELECT symbol, MIN(from_date) AS from_date FROM "StockPricesYahooMasterData" GROUP BY symbol
	) AS H ON A.SYMBOL = H.SYMBOL;