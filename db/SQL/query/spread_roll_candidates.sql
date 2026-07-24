-- spread_roll_candidates.sql
-- Roll-Kandidaten für einen bestehenden Bull-Put-Spread (Short-Put + Long-Put).
-- Liefert je passenden Short-Put die zugehörige Long-Seite bei (Short − Breite),
-- mit vorberechnetem Netto-Credit des Spreads. Die Aufteilung auf die 3 Roll-Stufen
-- (Short tiefer / gleicher Short / doppelte Kontrakte) macht src/spread_roll_calc.py bzw. die UI.
--
-- Breite bleibt fix (:spread_width) — beide Beine werden gemeinsam gerollt.
--
-- Muster: spreads_input.sql (Self-Join buy.strike = sell.strike - width) +
-- roll_candidates.sql (aktuelle Kette eines Symbols im DTE-Fenster).
-- Quelle: "OptionDataMerged". Params: :symbol, :short_strike, :spread_width,
--         :dte_min, :dte_max, :min_oi, :min_vol.
WITH puts AS (
    SELECT
        o.symbol,
        o.strike_price,
        o.expiration_date,
        o.days_to_expiration,
        o.premium_option_price,
        o.open_interest,
        o.day_volume,
        o.greeks_delta,
        o.implied_volatility,
        o.iv_rank,
        o.live_stock_price
    FROM "OptionDataMerged" o
    WHERE o.symbol = :symbol
      AND o.contract_type = 'put'
      AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
      AND o.premium_option_price > 0
)
SELECT
    sell.symbol,
    sell.expiration_date,
    sell.days_to_expiration                                   AS dte,
    ROUND(sell.live_stock_price::numeric, 2)                  AS price,
    -- Short-Bein (verkauft)
    ROUND(sell.strike_price::numeric, 2)                      AS short_strike,
    ROUND(sell.premium_option_price::numeric, 2)              AS short_premium,
    sell.open_interest                                        AS short_oi,
    sell.day_volume                                           AS short_volume,
    ROUND(sell.greeks_delta::numeric, 3)                      AS short_delta,
    ROUND(sell.iv_rank::numeric, 2)                           AS iv_rank,
    -- Long-Bein (gekauft, Short − Breite)
    ROUND(buy.strike_price::numeric, 2)                       AS long_strike,
    ROUND(buy.premium_option_price::numeric, 2)               AS long_premium,
    buy.open_interest                                         AS long_oi,
    buy.day_volume                                            AS long_volume,
    -- Spread-Kennzahlen
    :spread_width                                             AS width,
    ROUND((sell.premium_option_price - buy.premium_option_price)::numeric, 2) AS net_credit
FROM puts sell
INNER JOIN puts buy
    ON  sell.symbol = buy.symbol
    AND sell.expiration_date = buy.expiration_date
    AND buy.strike_price = sell.strike_price - :spread_width
WHERE sell.strike_price <= :short_strike        -- Short tiefer/gleich (Stufe 1/2/3)
  AND sell.open_interest >= :min_oi
  AND sell.day_volume    >= :min_vol
ORDER BY sell.expiration_date, sell.strike_price DESC;
