WITH FilteredCalls AS (
    SELECT
        symbol,
        company_name,
        company_sector,
        LIVE_STOCK_PRICE AS stock_price,
        strike_price,
        day_close AS premium,
        days_to_expiration AS DTE,
        expiration_date,
        abs(greeks_delta) AS delta,
        implied_volatility AS iv,
        open_interest,
        day_volume AS volume,
        earnings_date AS earnings_date_next,
        days_to_earnings,
        "20_day_MA",
        "50_day_MA",
        "200_day_MA",
        iv_rank,
        iv_percentile,
        ROW_NUMBER() OVER (
            PARTITION BY symbol
            ORDER BY ABS(abs(greeks_delta) - :delta_target) ASC
        ) AS delta_rank
    FROM
        "OptionDataMerged"
    WHERE
        contract_type = 'call'
        AND expiration_date = :expiration_date
        AND strike_price <= LIVE_STOCK_PRICE
        AND open_interest >= :min_open_interest
        AND day_close > 0
        AND LIVE_STOCK_PRICE > 0
)
SELECT * FROM FilteredCalls
WHERE delta_rank <= :max_per_symbol
ORDER BY symbol, delta_rank
