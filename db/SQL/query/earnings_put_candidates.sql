-- Earnings Put Scanner — Put candidates for a single symbol
-- Finds weekly puts expiring within 10 days,
-- with strike below (live_stock_price - expected_move)
-- Stock price from StockData for reliability
SELECT
    o.expiration_date,
    o.days_to_expiration,
    o.strike_price,
    o.premium_option_price,
    ROUND(CAST(o.premium_option_price AS NUMERIC) / NULLIF(CAST(o.strike_price AS NUMERIC), 0) * 100, 2) AS premium_pct,
    o.open_interest,
    o.implied_volatility,
    o.greeks_delta,
    s."FinData_currentPrice"  AS live_stock_price,
    o.expected_move
FROM "OptionDataMerged" o
JOIN "StockData" s ON s.symbol = o.symbol
WHERE
    o.symbol        = :symbol
    AND o.contract_type = 'put'
    AND o.days_to_expiration BETWEEN 1 AND 10
    AND o.open_interest > :min_oi
    AND o.premium_option_price > 0
ORDER BY o.expiration_date ASC, o.strike_price DESC
