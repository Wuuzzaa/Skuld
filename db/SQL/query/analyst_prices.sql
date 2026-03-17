SELECT
    symbol,
    live_stock_price AS close,
    analyst_mean_target,
    -- NULL recommendation, -- replace later with own recommendation based on technical indicators
    -- NULL "Recommend.All", -- replace later with own recommendation based on technical indicators
    "target-close$",
    "target-close%"
FROM
    "StockData"
WHERE analyst_mean_target IS NOT NULL;