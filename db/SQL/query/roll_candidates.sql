-- roll_candidates.sql
-- Aktuelle PUT-Optionskette eines Symbols als Roll-Kandidaten.
-- Liefert alle Puts im DTE-Fenster mit Strike <= K (bestehender Strike):
--   * Strike <  K  -> Kandidaten für Stufe 1 (gleiche Kontrakte) und Stufe 3 (2 Kontrakte)
--   * Strike =  K  -> Kandidaten für Stufe 2 (gleicher Basispreis)
-- Die Aufteilung auf die 3 Stufen erfolgt in src/roll_support_calc.py / der UI.
--
-- Quelle: "OptionDataMerged" (aktuelle Kette). Spaltennamen gegen bestehende
-- Queries (covered_call_scanner.sql, iron_condor_input.sql) verifiziert.
-- Params: :symbol, :K, :dte_min, :dte_max, :min_oi, :min_vol, :delta_min, :delta_max
--
-- Liquiditäts-Vorfilter: open_interest und day_volume vorhanden/> 0.
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
  AND o.contract_type = 'put'
  AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
  AND o.strike_price <= :K
  AND o.premium_option_price > 0
  AND o.open_interest >= :min_oi
  AND o.day_volume >= :min_vol
  AND o.greeks_delta IS NOT NULL
  AND o.greeks_delta BETWEEN :delta_min AND :delta_max
ORDER BY o.strike_price DESC, o.days_to_expiration ASC
