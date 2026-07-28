-- option_chain_symbol.sql
-- Volle Optionskette (Puts UND Calls) eines Symbols für EINEN Verfall.
-- Für die Broker-Ketten-Ansicht im Spread-Roller (Calls | Strike | Puts).
-- Quelle: "OptionDataMerged". KEIN bid/ask vorhanden -> premium_option_price = Last.
-- Params: :symbol, :expiration_date
SELECT
    o.contract_type,
    o.strike_price,
    o.premium_option_price,
    o.greeks_delta,
    o.open_interest,
    o.day_volume,
    o.implied_volatility,
    o.live_stock_price,
    o.expiration_date,
    o.days_to_expiration
FROM "OptionDataMerged" o
WHERE o.symbol = :symbol
  AND o.expiration_date = :expiration_date
ORDER BY o.strike_price ASC
