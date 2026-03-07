SELECT
    symbol,
    snapshot_date,
    open,
    high,
    low,
    close,
    volume
FROM "StockPricesYahooHistoryDaily"
WHERE symbol = ANY(:symbols)
AND snapshot_date > CURRENT_DATE - INTERVAL '3 year'
ORDER BY symbol ASC, snapshot_date ASC ;