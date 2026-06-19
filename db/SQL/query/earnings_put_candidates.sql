-- Earnings Put Scanner — Put candidates for a single symbol
-- Finds weekly puts expiring in the same week as earnings,
-- with strike below (live_stock_price - expected_move)
SELECT
    expiration_date,
    days_to_expiration,
    strike_price,
    premium_option_price,
    ROUND(CAST(premium_option_price AS NUMERIC) / NULLIF(CAST(strike_price AS NUMERIC), 0) * 100, 2) AS premium_pct,
    open_interest,
    implied_volatility,
    greeks_delta,
    live_stock_price,
    expected_move
FROM "OptionDataMerged"
WHERE
    symbol          = :symbol
    AND contract_type = 'put'
    AND days_to_expiration BETWEEN 1 AND 10
    AND open_interest > :min_oi
    AND premium_option_price > 0
ORDER BY expiration_date ASC, strike_price DESC
