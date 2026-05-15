WITH FilteredCalls AS (
    SELECT
        symbol,
        company_name,
        company_sector,
        live_stock_price AS stock_price,
        strike_price,
        day_close AS premium,
        days_to_expiration AS "DTE",
        expiration_date,
        abs(greeks_delta) AS delta,
        implied_volatility AS iv,
        open_interest,
        day_volume AS volume,
        earnings_date AS earnings_date_next,
        days_to_earnings,
        "SMA_20",
        "SMA_50",
        "SMA_200",
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
        AND strike_price <= live_stock_price
        AND open_interest >= :min_open_interest
        AND day_close > 0
        AND live_stock_price > 0
)
SELECT * FROM FilteredCalls
WHERE delta_rank <= :max_per_symbol
ORDER BY symbol, delta_rank
