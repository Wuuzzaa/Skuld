SELECT DISTINCT
    symbol,
    "Company",
    ROUND(live_stock_price::numeric, 2) AS live_stock_price,
    ROUND("Current-Div"::numeric, 2) AS "Current Dividend",
    "Classification",
    ROUND(iv::numeric, 2) AS iv,
    ROUND(iv_low::numeric, 2) AS iv_low,
    ROUND(iv_high::numeric, 2) AS iv_high,
    ROUND(iv_rank::numeric, 2) AS iv_rank,
    ROUND(iv_percentile::numeric, 2) AS iv_percentile,
    ROUND(historical_volatility_30d::numeric, 2) AS historical_volatility_30d,
    ROUND("KeyStats_beta"::numeric, 2) AS Beta
FROM "OptionDataMerged"
WHERE symbol = :symbol;