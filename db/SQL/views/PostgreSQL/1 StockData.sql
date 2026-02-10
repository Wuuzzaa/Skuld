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
    d.iv_percentile
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
	LEFT OUTER JOIN "StockImpliedVolatilityMassive" AS d ON a.symbol = d.symbol;