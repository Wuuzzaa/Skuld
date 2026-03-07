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
ORDER BY symbol ASC, snapshot_date ASC ;