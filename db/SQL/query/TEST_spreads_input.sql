-- Schritt 1: Sell-Optionen mit dem höchsten Delta pro Symbol auswählen
WITH SellOptions AS (
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
        AND contract_type = :sell_option_type  -- z. B. 'put'
        AND abs(delta) <= :delta_target
        AND open_interest >= :min_open_interest
),
SelectedSellOptions AS (
    SELECT
        symbol,
        strike AS sell_strike
    FROM
        SellOptions
    WHERE
        row_num = 1
)

-- Schritt 2: Buy-Optionen mit Strike = (Sell-Strike - 5) finden
SELECT
    'Sell' AS strategy,
    s.symbol,
    s.expiration_date,
    s.option_type,
    s.strike,
    s.mid,
    s.delta,
    s.iv,
    s.theta,
    s.close,
    s.earnings_date,
    s.days_to_expiration,
    s.days_to_ernings,
    s.option_open_interest,
    s.expected_move
FROM
    SellOptions s
WHERE
    s.row_num = 1

UNION ALL

SELECT
    'Buy' AS strategy,
    o.symbol,
    o.expiration_date,
    o.contract_type AS option_type,
    o.strike_price AS strike,
    o.day_close AS mid,
    abs(o.greeks_delta) AS delta,
    o.implied_volatility AS iv,
    o.greeks_theta AS theta,
    o.close,
    o.earnings_date,
    o.days_to_expiration,
    o.days_to_ernings,
    o.open_interest AS option_open_interest,
    o.expected_move
FROM
    OptionDataMerged o
INNER JOIN SelectedSellOptions sell
    ON o.symbol = sell.symbol
    AND o.strike_price = (sell.sell_strike - 5)
WHERE
    o.expiration_date = :expiration_date
    AND o.contract_type = :buy_option_type  -- z. B. 'call'
    AND abs(o.delta) <= :delta_target
    AND o.open_interest >= :min_open_interest
ORDER BY
    strategy DESC, symbol;
