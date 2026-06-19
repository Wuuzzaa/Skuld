-- Earnings Put Scanner
-- Step 1: Candidate scan — one row per symbol with upcoming earnings
-- Filters: MarketCap > 2B, Price 15–250$, Earnings within :days_ahead days
SELECT DISTINCT ON (symbol)
    symbol,
    earnings_date,
    days_to_earnings,
    live_stock_price,
    expected_move,
    ROUND(CAST(expected_move AS NUMERIC) / NULLIF(CAST(live_stock_price AS NUMERIC), 0) * 100, 1) AS expected_move_pct,
    iv_rank,
    iv_percentile,
    historical_volatility_30d,
    "Summary_marketCap"                      AS market_cap,
    "Summary_trailingPE"                     AS trailing_pe,
    "Summary_averageVolume"                  AS avg_volume,
    dividend_classification,
    "KeyStats_profitMargins"                 AS profit_margin
FROM "OptionDataMerged"
WHERE
    days_to_earnings BETWEEN 0 AND :days_ahead
    AND "Summary_marketCap" > 2000000000
    AND live_stock_price BETWEEN 15 AND 250
ORDER BY symbol, days_to_earnings ASC
