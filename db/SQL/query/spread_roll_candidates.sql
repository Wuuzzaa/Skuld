-- spread_roll_candidates.sql
-- Roll-Kandidaten für einen bestehenden vertikalen Spread (2026-07-27 generalisiert
-- von Bull-Put-only auf alle 4 Arten: Bull-Put/Bear-Call (Credit), Bull-Call/Bear-Put (Debit)).
--
-- Liefert je passendem "Sell"-Bein das zugehörige "Buy"-Bein bei fixer Breite, mit den
-- rohen Prämien beider Beine (Netto-Vorzeichen macht Python je Spread-Art). Die Aufteilung
-- auf die benannten Roll-Prinzipien (vertikal/horizontal/diagonal/verdoppeln) macht die UI.
--
-- Breite bleibt fix (:spread_width) — beide Beine werden gemeinsam gerollt.
-- Die 4-Wege-Bein-Geometrie ist aus spreads_input.sql (Z.99-112) übernommen.
--
-- Quelle: "OptionDataMerged".
-- Params: :symbol, :contract_type ('put'|'call'), :strategy_type ('credit'|'debit'),
--         :spread_width, :dte_min, :dte_max, :min_oi, :min_vol, :strike_lo, :strike_hi.
WITH opts AS (
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
      AND o.contract_type = :contract_type
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
    -- Long-Bein (gekauft)
    ROUND(buy.strike_price::numeric, 2)                       AS long_strike,
    ROUND(buy.premium_option_price::numeric, 2)               AS long_premium,
    buy.open_interest                                         AS long_oi,
    buy.day_volume                                            AS long_volume,
    -- Spread-Kennzahlen
    :spread_width                                             AS width,
    -- net_credit (Rückwärtskompat-Alias): Sell − Buy. Bei Credit = positiver Credit,
    -- bei Debit i.d.R. negativ (Buy teurer). Python interpretiert je Spread-Art.
    ROUND((sell.premium_option_price - buy.premium_option_price)::numeric, 2) AS net_credit,
    ROUND(ABS(sell.premium_option_price - buy.premium_option_price)::numeric, 2) AS net_price
FROM opts sell
INNER JOIN opts buy
    ON  sell.symbol = buy.symbol
    AND sell.expiration_date = buy.expiration_date
    AND buy.strike_price = (
        CASE
            WHEN :strategy_type = 'credit' THEN
                CASE
                    WHEN :contract_type = 'put'  THEN sell.strike_price - :spread_width
                    WHEN :contract_type = 'call' THEN sell.strike_price + :spread_width
                END
            WHEN :strategy_type = 'debit' THEN
                CASE
                    WHEN :contract_type = 'put'  THEN sell.strike_price + :spread_width
                    WHEN :contract_type = 'call' THEN sell.strike_price - :spread_width
                END
        END)
WHERE sell.strike_price BETWEEN :strike_lo AND :strike_hi   -- Fenster (Python je Spread-Art)
  AND sell.open_interest >= :min_oi
  AND sell.day_volume    >= :min_vol
ORDER BY sell.expiration_date, sell.strike_price DESC;
