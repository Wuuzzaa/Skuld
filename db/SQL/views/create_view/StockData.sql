DROP VIEW IF EXISTS "StockData";

CREATE VIEW
    "StockData" AS
SELECT
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
        julianday (b.earnings_date) - julianday ('now') AS INTEGER
    ) AS days_to_earnings,
    CASE
        WHEN c.symbol IS NOT NULL THEN TRUE
        ELSE FALSE
    END as has_analyst_price_target,
    c.analyst_mean_target
FROM
    "StockPrice" AS a
    LEFT OUTER JOIN (
        SELECT
            symbol,
            CASE WHEN earnings_date LIKE '%.%.%' THEN
            substr (earnings_date, 7, 4) || '-' || substr (earnings_date, 4, 2) || '-' || substr (earnings_date, 1, 2)
            else NULL
            end as earnings_date
        FROM
            "EarningDates"
    ) AS b ON a.symbol = b.symbol
    LEFT OUTER JOIN "AnalystPriceTargets" AS c ON a.symbol = c.symbol;