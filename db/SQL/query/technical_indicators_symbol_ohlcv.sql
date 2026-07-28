SELECT
    symbol,
    date AS snapshot_date,
    open,
    high,
    low,
    close,
    volume
FROM "StockPricesYahooHistory"
WHERE symbol = ANY(:symbols)
AND date > CURRENT_DATE - INTERVAL '3 year'
ORDER BY symbol ASC, date ASC ;