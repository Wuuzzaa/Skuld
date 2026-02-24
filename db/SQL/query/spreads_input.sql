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
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY abs(greeks_delta) DESC) AS row_num,
        analyst_mean_target,
        -- NULL AS recommendation, -- replace later with own recommendation based on technical indicators
        day_volume,
        company_industry,
        company_sector,
        historical_volatility_30d,
        iv_rank,
        iv_percentile
    FROM
        "OptionDataMerged"
    WHERE
        expiration_date = :expiration_date
        AND contract_type = :option_type
        AND abs(greeks_delta) <= :delta_target
        AND open_interest >= :min_open_interest
        AND day_volume >= :min_day_volume
        AND iv_rank >= :min_iv_rank
        AND iv_percentile >= :min_iv_percentile
),

SelectedSellOptions AS (
    SELECT
        symbol,
        strike AS sell_strike,
        expiration_date,
        option_type,
        last_option_price AS sell_last_option_price,
        delta AS sell_delta,
        iv AS sell_iv,
        theta AS sell_theta,
        close AS sell_close,
        earnings_date,
        days_to_expiration,
        days_to_earnings,
        option_open_interest AS sell_open_interest,
        expected_move AS sell_expected_move,
        analyst_mean_target,
        -- recommendation, -- replace later with own recommendation based on technical indicators
        day_volume AS sell_day_volume,
        company_industry,
        company_sector,
        historical_volatility_30d,
        iv_rank,
        iv_percentile
    FROM
        FilteredOptions
    WHERE
        row_num = 1
)

--spread data
SELECT
    -- symbol data
    sell.symbol,
    sell.expiration_date,
    sell.option_type,
    sell.sell_close AS close,
    sell.earnings_date,
    sell.days_to_expiration,
    sell.days_to_earnings,
    sell.analyst_mean_target,
    -- sell.recommendation, -- replace later with own recommendation based on technical indicators
    sell.company_industry,
    sell.company_sector,
    sell.historical_volatility_30d,
    sell.iv_rank,
    sell.iv_percentile,
    -- sell option
    sell.sell_strike,
    sell.sell_last_option_price,
    sell.sell_delta,
    sell.sell_iv,
    sell.sell_theta,
    sell.sell_open_interest,
    sell.sell_expected_move,
    sell.sell_day_volume,
    -- buy option
    buy.strike               AS buy_strike,
    buy.last_option_price    AS buy_last_option_price,
    buy.delta                AS buy_delta,
    buy.iv                   AS buy_iv,
    buy.theta                AS buy_theta,
    buy.option_open_interest AS buy_open_interest,
    buy.expected_move        AS buy_expected_move
FROM
    SelectedSellOptions sell
INNER JOIN
    FilteredOptions buy
    ON sell.symbol = buy.symbol
    AND buy.strike = (
        CASE
            WHEN sell.option_type = 'put' THEN sell.sell_strike - :spread_width
            WHEN sell.option_type = 'call' THEN sell.sell_strike + :spread_width
        END
    );
