DROP VIEW IF EXISTS StockData;

CREATE VIEW StockData AS
SELECT 
 a.symbol,
 a.analyst_mean_target,
 b.earnings_date
FROM 
 AnalystPriceTargets AS a
JOIN 
 EarningDates AS b
ON 
 a.symbol = b.symbol;