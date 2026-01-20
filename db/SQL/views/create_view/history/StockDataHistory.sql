DROP VIEW IF EXISTS "StockDataHistory";
CREATE VIEW
    "StockDataHistory" AS
SELECT
    a.date,
    a.symbol,
    a.live_stock_price,
    a.price_source,
    a.live_price_timestamp,
    CASE
        WHEN b.symbol IS NOT NULL THEN TRUE
        ELSE FALSE
    END as has_earnings_date,
    b.earnings_date,
    CAST(
        julianday (b.earnings_date) - julianday (a.date) AS INTEGER
    ) AS days_to_earnings,
    CASE
        WHEN c.symbol IS NOT NULL THEN TRUE
        ELSE FALSE
    END as has_analyst_price_target,
    c.analyst_mean_target
FROM
    StockPriceHistory AS a
    LEFT OUTER JOIN (
        SELECT
            date,
            symbol,
            CASE
                WHEN earnings_date LIKE '%.%.%' THEN substr (earnings_date, 7, 4) || '-' || substr (earnings_date, 4, 2) || '-' || substr (earnings_date, 1, 2)
                else NULL
            end as earnings_date
        FROM
            EarningDatesHistory
    ) AS b ON a.symbol = b.symbol
    AND a.date = b.date
    LEFT OUTER JOIN AnalystPriceTargetsHistory AS c ON a.symbol = c.symbol
    AND a.date = c.date;