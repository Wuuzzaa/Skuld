SELECT
    symbol,
    company_name,
    company_sector AS sector,
    company_industry AS industry,
    ROUND("RSL"::numeric, 4) AS rsl,
    live_stock_price AS price
FROM
    "StockData"
WHERE
    symbol = ANY(:symbols)
    AND "RSL" IS NOT NULL