WITH FilteredOptions AS (
    SELECT
        symbol,
        expiration_date,
        contract_type AS option_type,
        strike_price AS strike,
        day_close AS last_option_price,
        abs(greeks_delta) AS delta,
        implied_volatility AS iv,
        greeks_theta AS theta,
        LIVE_STOCK_PRICE AS close,
        earnings_date,
        days_to_expiration,
        days_to_earnings,
        open_interest AS option_open_interest,
        expected_move,
        analyst_mean_target,
        day_volume,
        day_last_updated,
        company_name,
        company_industry,
        company_sector,
        historical_volatility_30d,
        iv_rank,
        iv_percentile,
        last_updated_option_data,
        last_updated_stock_data
    FROM
        "OptionDataMerged"
    WHERE
        open_interest >= :min_open_interest
        AND day_volume >= :min_day_volume
        AND (:min_iv_rank <= 0 OR iv_rank IS NULL OR iv_rank >= :min_iv_rank)
        AND (:min_iv_percentile <= 0 OR iv_percentile IS NULL OR iv_percentile >= :min_iv_percentile)
),

RankedOptions AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, expiration_date, option_type
            ORDER BY abs(delta - :delta_target) ASC
        ) as delta_rank
    FROM
        FilteredOptions
    WHERE
        expiration_date = :expiration_date
        AND option_type = :option_type
)

SELECT
    symbol,
    expiration_date,
    option_type,
    close,
    earnings_date,
    company_name AS "Company",
    days_to_expiration,
    days_to_earnings,
    analyst_mean_target,
    company_industry,
    company_sector,
    historical_volatility_30d,
    iv_rank,
    iv_percentile,
    strike,
    last_option_price,
    delta,
    iv,
    theta,
    option_open_interest AS open_interest,
    expected_move,
    day_volume,
    day_last_updated,
    last_updated_option_data,
    last_updated_stock_data
FROM
    RankedOptions
WHERE
    delta_rank <= :delta_candidates;
