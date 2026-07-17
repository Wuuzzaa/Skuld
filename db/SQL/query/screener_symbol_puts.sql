-- screener_symbol_puts.sql
-- Aktuell verkaufbare PUTS eines Symbols im DTE-Fenster (Screener-Detail).
-- Kein Strike-Filter (anders als roll_candidates.sql) — alle liquiden Puts.
-- Kennzahlen wie in der Spread-Detailansicht (Delta, Theta, IV, Exp. Move) + Rohwerte
-- für Black-Scholes (live_stock_price, implied_volatility).
-- Quelle: "OptionDataMerged". Params: :symbol, :dte_min, :dte_max,
--         :min_oi, :min_vol, :min_premium_share
SELECT
    o.symbol,
    o.strike_price,
    o.expiration_date,
    o.days_to_expiration,
    o.premium_option_price,
    o.open_interest,
    o.day_volume,
    o.greeks_delta,
    o.greeks_theta,
    o.implied_volatility,
    o.iv_rank,
    o.iv_percentile,
    o.expected_move,
    o.live_stock_price
FROM "OptionDataMerged" o
WHERE o.symbol = :symbol
  AND o.contract_type = 'put'
  AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
  AND o.premium_option_price >= :min_premium_share
  AND o.open_interest >= :min_oi
  AND o.day_volume >= :min_vol
ORDER BY o.expiration_date ASC, o.strike_price ASC
