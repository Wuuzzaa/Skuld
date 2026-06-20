SELECT 
    date as date,
    symbol,
    ROUND(iv::numeric * 100, 2) AS iv,
    ROUND(iv_low::numeric * 100, 2) AS iv_low,
    ROUND(iv_high::numeric * 100, 2) AS iv_high,
    ROUND(iv_rank::numeric, 2) AS iv_rank,
    ROUND(iv_percentile::numeric, 2) AS iv_percentile
FROM "StockImpliedVolatilityMassiveHistory" AS iv_history
WHERE symbol = :symbol
AND date <= CURRENT_DATE
ORDER BY date DESC;