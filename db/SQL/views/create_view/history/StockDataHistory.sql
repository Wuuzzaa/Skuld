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
    ) AS days_to_ernings,
    CASE
        WHEN c.symbol IS NOT NULL THEN TRUE
        ELSE FALSE
    END as has_analyst_price_target,
    c.analyst_mean_target,
    -- Barchart Data
    d.implied_volatility,
    d.historical_volatility,
    d.iv_percentile,
    d.iv_rank,
    d.iv_high,
    d.iv_low,
    d.put_call_vol_ratio,
    d.put_call_oi_ratio,
    d.todays_volume,
    d.volume_avg_30d,
    d.todays_open_interest,
    d.open_int_30d
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
    AND a.date = c.date
    LEFT OUTER JOIN StockDataBarchartHistory AS d ON a.symbol = d.symbol
    AND a.date = d.date;