SELECT DISTINCT
    s.symbol,
    s.company_name,
    s.company_sector AS sector,
    s.company_industry AS industry,
    s.company_country AS country,
    ROUND(s.live_stock_price::numeric, 2) AS price,
    ROUND(s.iv::numeric * 100, 2) AS iv,
    ROUND(s.iv_rank::numeric, 2) AS iv_rank,
    ROUND(s."RSL"::numeric, 4) AS rsl,
    ROUND(s."KeyStats_beta"::numeric, 2) AS beta,
    s.dividend_classification,
    CASE
        WHEN m.exchange_mic = 'XNAS' THEN 'NASDAQ'
        WHEN m.exchange_mic = 'XNYS' THEN 'NYSE'
        WHEN m.exchange_mic = 'ARCX' THEN 'AMEX'
        WHEN m.exchange_mic = 'XASE' THEN 'AMEX'
        ELSE m.exchange_mic
    END AS exchange
FROM "StockData" s
LEFT JOIN "StockSymbolsMassive" m ON m.symbol = s.symbol
WHERE s.live_stock_price IS NOT NULL
ORDER BY s.symbol;
