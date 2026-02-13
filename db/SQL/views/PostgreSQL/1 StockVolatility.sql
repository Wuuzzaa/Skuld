CREATE OR REPLACE VIEW "StockVolatility" AS
WITH 
StockPrices AS (
    SELECT 
        CURRENT_DATE AS date,
        symbol,
        adjclose
    FROM "StockPricesYahoo"
    WHERE EXTRACT(ISODOW FROM CURRENT_DATE) NOT IN (6, 7) -- Exclude weekends
    UNION ALL
    SELECT 
        snapshot_date AS date,
        symbol,
        adjclose
    FROM "StockPricesYahooHistoryDaily"
    WHERE snapshot_date <> CURRENT_DATE
    AND snapshot_date >= CURRENT_DATE - INTERVAL '60 day'
),
DailyReturns AS (
    -- Step 1: Get the previous day's price and calculate log return
    SELECT 
        ROW_NUMBER() OVER(PARTITION BY symbol ORDER BY date DESC) AS trading_day,
        symbol,
        adjclose,
        LAG(adjclose) OVER (PARTITION BY symbol ORDER BY date) as prev_close
    FROM StockPrices
),
LogReturns AS (
    -- Step 2: Compute the natural log of the ratio
    SELECT 
        symbol,
        LN(adjclose / NULLIF(prev_close, 0)) as log_return
    FROM DailyReturns
    WHERE prev_close IS NOT NULL AND prev_close > 0
	AND trading_day <=30
)
-- Step 3: Calculate 30-day rolling volatility annualized
SELECT
    symbol,
    STDDEV(log_return) * SQRT(252) AS historical_volatility_30d
FROM LogReturns
group by symbol;