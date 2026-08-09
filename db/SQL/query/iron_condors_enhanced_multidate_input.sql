-- Iron Condors Enhanced Multi-Date Query
-- __EXP_LIST__ wird durch :d0, :d1, ... ersetzt (eine Zeile pro Termin im DTE-Range).
-- WICHTIG: keine Doppelpunkt-Parameter-Beispiele in Kommentaren schreiben!
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
        open_interest IS NOT NULL AND open_interest >= :min_open_interest
        AND day_volume IS NOT NULL AND day_volume >= :min_day_volume
        AND (:min_iv_rank <= 0 OR iv_rank IS NULL OR iv_rank >= :min_iv_rank)
        AND (:min_iv_percentile <= 0 OR iv_percentile IS NULL OR iv_percentile >= :min_iv_percentile)
        AND expiration_date IN (__EXP_LIST__)
        AND contract_type = :option_type
),

TargetOptions AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, expiration_date, option_type
            ORDER BY abs(delta - :delta_target) ASC
        ) as delta_rank
    FROM
        FilteredOptions
)

SELECT
    sell.symbol,
    sell.expiration_date,
    sell.option_type,
    sell.close,
    sell.earnings_date,
    sell.company_name AS "Company",
    sell.days_to_expiration,
    sell.days_to_earnings,
    sell.analyst_mean_target,
    sell.company_industry,
    sell.company_sector,
    sell.historical_volatility_30d,
    sell.iv_rank,
    sell.iv_percentile,
    sell.strike AS sell_strike,
    sell.last_option_price AS sell_last_option_price,
    sell.delta AS sell_delta,
    sell.iv AS sell_iv,
    sell.theta AS sell_theta,
    sell.option_open_interest AS sell_open_interest,
    sell.expected_move AS sell_expected_move,
    sell.day_volume AS sell_day_volume,
    sell.day_last_updated AS sell_last_updated,
    buy.strike AS buy_strike,
    buy.last_option_price AS buy_last_option_price,
    buy.delta AS buy_delta,
    buy.iv AS buy_iv,
    buy.theta AS buy_theta,
    buy.option_open_interest AS buy_open_interest,
    buy.expected_move AS buy_expected_move,
    buy.day_volume AS buy_day_volume,
    buy.day_last_updated AS buy_last_updated,
    buy.last_updated_option_data,
    buy.last_updated_stock_data
FROM
    TargetOptions sell
INNER JOIN
    FilteredOptions buy
    ON sell.symbol = buy.symbol
    AND sell.expiration_date = buy.expiration_date
    AND sell.option_type = buy.option_type
    AND buy.strike != sell.strike
    AND (
        CASE
            WHEN sell.option_type = 'put'  THEN buy.strike BETWEEN sell.strike - :spread_width AND sell.strike - :spread_width_min
            WHEN sell.option_type = 'call' THEN buy.strike BETWEEN sell.strike + :spread_width_min AND sell.strike + :spread_width
        END
    )
WHERE
    sell.delta_rank <= :delta_candidates;
