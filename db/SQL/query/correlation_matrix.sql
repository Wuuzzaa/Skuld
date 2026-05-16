SELECT symbol, snapshot_date, close
FROM "StockPricesYahooHistoryDaily"
WHERE symbol = ANY(:symbols)
  AND snapshot_date >= CURRENT_DATE - CAST(:lookback_days || ' days' AS INTERVAL)
ORDER BY symbol, snapshot_date
