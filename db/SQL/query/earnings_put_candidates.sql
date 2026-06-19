-- Earnings Put Scanner — Put candidates for a single symbol
-- Finds puts on the first available expiry AFTER the earnings date (up to 21 DTE).
-- Stock price from StockData for reliability
WITH earnings AS (
    SELECT DISTINCT ON (symbol) earnings_date
    FROM "OptionDataMerged"
    WHERE symbol = :symbol
    ORDER BY symbol, days_to_earnings ASC
),
post_earnings_expiry AS (
    SELECT MIN(o.expiration_date) AS target_expiry
    FROM "OptionDataMerged" o
    JOIN earnings e ON o.expiration_date > e.earnings_date
    WHERE o.symbol = :symbol
      AND o.contract_type = 'put'
      AND o.days_to_expiration BETWEEN 1 AND 21
      AND o.open_interest > :min_oi
      AND o.premium_option_price > 0
)
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
JOIN post_earnings_expiry pe ON o.expiration_date = pe.target_expiry
WHERE
    o.symbol        = :symbol
    AND o.contract_type = 'put'
    AND o.open_interest > :min_oi
    AND o.premium_option_price > 0
ORDER BY o.strike_price DESC

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
JOIN post_earnings_expiry pe ON o.expiration_date = pe.target_expiry
WHERE
    o.symbol        = :symbol
    AND o.contract_type = 'put'
    AND o.open_interest > :min_oi
    AND o.premium_option_price > 0
ORDER BY o.strike_price DESC
