-- screener_symbol_puts.sql
-- Aktuell verkaufbare PUTS eines Symbols im DTE-Fenster (Screener-Detail).
-- Kein Strike-Filter (anders als roll_candidates.sql) — alle liquiden Puts,
-- sortiert nächst-am-Geld zuerst.
-- Quelle: "OptionDataMerged". Params: :symbol, :dte_min, :dte_max
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
    o.live_stock_price
FROM "OptionDataMerged" o
WHERE o.symbol = :symbol
  AND o.contract_type = 'put'
  AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
  AND o.premium_option_price > 0
  AND o.open_interest > 0
  AND o.day_volume > 0
ORDER BY ABS(o.strike_price - o.live_stock_price) ASC, o.days_to_expiration ASC
