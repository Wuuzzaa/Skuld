SELECT
    a.symbol,
    c.name AS company_name,
    c.sector AS sector,
    c.industry AS industry,
    ROUND(b."RSL"::numeric, 4) AS rsl,
    a.close AS price
FROM
    "StockPricesYahoo" AS a
    LEFT OUTER JOIN "TechnicalIndicatorsCalculated" AS b
	ON a.SYMBOL = b.SYMBOL
    LEFT OUTER JOIN 
	"StockAssetProfilesYahooMasterData" AS c
    ON a.symbol = c.symbol
WHERE
    a.symbol = ANY(:symbols)
    AND b."RSL" IS NOT NULL