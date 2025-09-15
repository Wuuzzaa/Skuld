DROP VIEW IF EXISTS StockData;

CREATE VIEW
    StockData AS
SELECT
    a.symbol,
    a.analyst_mean_target,
    b.earnings_date,
    c.live_stock_price,
    c.price_source,
    c.live_price_timestamp
FROM
    AnalystPriceTargets AS a
    JOIN EarningDates AS b ON a.symbol = b.symbol
    JOIN StockPrice AS c ON a.symbol = c.symbol;