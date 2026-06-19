-- Earnings Put Scanner
-- Step 1: Candidate scan — one row per symbol with upcoming earnings
-- Filters: MarketCap > 2B, Price 15–250$, Earnings within :days_ahead days
-- Stock price comes from StockData.FinData_currentPrice (reliable daily update)
SELECT DISTINCT ON (o.symbol)
    o.symbol,
    o.earnings_date,
    o.days_to_earnings,
    s."FinData_currentPrice"                  AS live_stock_price,
    o.expected_move,
    ROUND(
        CAST(o.expected_move AS NUMERIC)
        / NULLIF(CAST(s."FinData_currentPrice" AS NUMERIC), 0) * 100
    , 1)                                      AS expected_move_pct,
    o.iv_rank,
    o.iv_percentile,
    o.historical_volatility_30d,
    o."Summary_marketCap"                     AS market_cap,
    o."Summary_trailingPE"                    AS trailing_pe,
    o."Summary_averageVolume"                 AS avg_volume,
    o.dividend_classification,
    o."KeyStats_profitMargins"                AS profit_margin
FROM "OptionDataMerged" o
JOIN "StockData" s ON s.symbol = o.symbol
WHERE
    o.days_to_earnings BETWEEN 0 AND :days_ahead
    AND o."Summary_marketCap" > 2000000000
    AND s."FinData_currentPrice" BETWEEN 15 AND 250
ORDER BY o.symbol, o.days_to_earnings ASC
