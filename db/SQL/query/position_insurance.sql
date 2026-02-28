SELECT
    symbol,
    expiration_date,
    strike_price,
    contract_type,
    day_close AS last_option_price,
    day_close AS option_price, -- Alias for consistency
    greeks_delta,
    greeks_theta,
    open_interest,
    -- Stock data from merged view
    live_stock_price, 
    live_stock_price AS stock_close, -- Fallback if live price is null
    days_to_expiration
FROM
    "OptionDataMerged"
WHERE
    symbol = :symbol
    AND contract_type IN ('put', 'call')
    AND expiration_date >= :today
ORDER BY
    contract_type ASC,
    expiration_date ASC,
    strike_price ASC;
