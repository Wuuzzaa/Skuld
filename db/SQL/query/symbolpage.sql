SELECT DISTINCT
    symbol,
    company_name AS "Company",
    ROUND(live_stock_price::numeric, 2) AS live_stock_price,
    ROUND("Current-Div"::numeric, 2) AS "Current Dividend",
    dividend_classification AS "Classification",
    dividend_growth_years,
    ROUND(iv::numeric * 100, 2) AS iv,
    ROUND(iv_low::numeric * 100, 2) AS iv_low,
    ROUND(iv_high::numeric * 100, 2) AS iv_high,
    ROUND(iv_rank::numeric, 2) AS iv_rank,
    ROUND(iv_percentile::numeric, 2) AS iv_percentile,
    days_of_options_data_history,
    ROUND(historical_volatility_30d::numeric * 100, 2) AS historical_volatility_30d,
    ROUND("KeyStats_beta"::numeric, 2) AS Beta
FROM "OptionDataMerged"
WHERE symbol = :symbol;