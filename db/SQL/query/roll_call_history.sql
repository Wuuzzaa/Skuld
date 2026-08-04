-- roll_call_history.sql
-- Listet die zu einem Einstiegsdatum in der Historie verfügbaren CALLS eines Symbols.
-- Der User wählt daraus seinen historisch eröffneten (Short) Call aus.
-- day_close am Einstiegsdatum dient als Vorschlag für die Eröffnungsprämie
-- (per "Echte Ausführungskurse"-Override überschreibbar).
--
-- Muster: roll_put_history.sql — identisch bis auf contract_type = 'call'.
-- Params: :symbol, :entry_date, :dte_min, :dte_max
SELECT
    a.option_osi,
    a.symbol,
    a.contract_type,
    a.expiration_date,
    a.strike_price,
    a.day_close AS premium_option_price,
    a.shares_per_contract,
    (a.expiration_date::date - CAST(:entry_date AS date)) AS days_to_expiration,
    b.close AS stock_close
FROM (
        SELECT * FROM "OptionDataMassiveHistory"
        WHERE date = CAST(:entry_date AS date)
            AND symbol = :symbol
            AND contract_type = 'call'
    UNION ALL
        SELECT CURRENT_DATE AS date, * FROM "OptionDataMassive"
        WHERE CAST(:entry_date AS date) = CURRENT_DATE
            AND symbol = :symbol
            AND contract_type = 'call'
) AS a
INNER JOIN (
        SELECT * FROM "StockPricesYahooHistory"
        WHERE date = CAST(:entry_date AS date)
            AND symbol = :symbol
    UNION ALL
        SELECT CURRENT_DATE AS date, * FROM "StockPricesYahoo"
        WHERE CAST(:entry_date AS date) = CURRENT_DATE
            AND symbol = :symbol
) AS b
    ON a.date = b.date AND a.symbol = b.symbol
WHERE a.symbol = :symbol
  AND a.expiration_date::date > CAST(:entry_date AS date)
  AND (a.expiration_date::date - CAST(:entry_date AS date)) BETWEEN :dte_min AND :dte_max
ORDER BY a.expiration_date ASC, a.strike_price ASC
