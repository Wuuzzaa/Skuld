SELECT
    snapshot_date,
    open,
    high,
    low,
    close,
    volume,
    dividends
FROM "StockPricesYahooHistoryDaily"
WHERE symbol = :symbol
ORDER BY snapshot_date ASC ;