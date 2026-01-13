WITH FilteredOptions AS (
    SELECT
        symbol,
        expiration_date,
        contract_type AS option_type,
        strike_price AS strike,
        day_close AS mid,
        abs(greeks_delta) AS delta,
        implied_volatility AS iv,
        greeks_theta AS theta,
        close,
        earnings_date,
        days_to_expiration,
        days_to_ernings,
        open_interest AS option_open_interest,
        expected_move,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY abs(greeks_delta) DESC) AS row_num
    FROM
        OptionDataMerged
    WHERE
        expiration_date = :expiration_date
        AND contract_type = :option_type
        AND abs(greeks_delta) <= :delta_target
        AND open_interest >= :min_open_interest
),

SelectedSellOptions AS (
    SELECT
        symbol,
        strike AS sell_strike,
        expiration_date,
        option_type,
        mid AS sell_mid,
        delta AS sell_delta,
        iv AS sell_iv,
        theta AS sell_theta,
        close AS sell_close,
        earnings_date,
        days_to_expiration,
        days_to_ernings,
        option_open_interest AS sell_open_interest,
        expected_move AS sell_expected_move
    FROM
        FilteredOptions
    WHERE
        row_num = 1
)

SELECT
    sell.symbol,
    sell.expiration_date,
    sell.option_type,
    sell.sell_close AS close,
    sell.earnings_date,
    sell.days_to_expiration,
    sell.days_to_ernings,
    sell.sell_strike,
    sell.sell_mid,
    sell.sell_delta,
    sell.sell_iv,
    sell.sell_theta,
    sell.sell_open_interest,
    sell.sell_expected_move,
    buy.strike AS buy_strike,  -- Hier wurde `strike_price` durch `strike` ersetzt
    buy.mid AS buy_mid,
    buy.delta AS buy_delta,
    buy.iv AS buy_iv,
    buy.theta AS buy_theta,
    buy.option_open_interest AS buy_open_interest,
    buy.expected_move AS buy_expected_move
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
