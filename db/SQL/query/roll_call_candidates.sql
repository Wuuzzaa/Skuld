-- roll_call_candidates.sql
-- Aktuelle CALL-Optionskette eines Symbols als Roll-Kandidaten für Short Calls.
-- Liefert alle Calls im DTE-Fenster mit Strike >= K (bestehender Strike):
--   * Strike >  K  -> Kandidaten für ↕️ Vertikal (höherer Strike, noch weiter OTM)
--   * Strike =  K  -> Kandidaten für ↔️ Horizontal (gleicher Strike, mehr Zeit)
-- Die Aufteilung erfolgt in der UI analog zum Put-Roller.
--
-- OTM für Short Calls = Strike ÜBER dem aktuellen Kurs (umgekehrt zu Puts).
-- Quelle: "OptionDataMerged" (aktuelle Kette).
-- Params: :symbol, :K, :dte_min, :dte_max, :min_oi, :min_vol, :delta_min, :delta_max
--
-- delta_min/:delta_max: für Short Calls sind Delta-Werte positiv (0.05–1.0).
SELECT
    o.symbol,
    o.contract_type,
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
  AND o.contract_type = 'call'
  AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
  AND o.strike_price >= :K
  AND o.premium_option_price > 0
  AND o.open_interest >= :min_oi
  AND o.day_volume >= :min_vol
  AND o.greeks_delta IS NOT NULL
  AND o.greeks_delta BETWEEN :delta_min AND :delta_max
ORDER BY o.strike_price ASC, o.days_to_expiration ASC
