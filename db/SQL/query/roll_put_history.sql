-- roll_put_history.sql
-- Listet die zu einem Einstiegsdatum in der Historie verfügbaren PUTS eines Symbols.
-- Der User wählt daraus seinen historisch eröffneten Put aus (Zeilenauswahl in der UI).
-- day_close am Einstiegsdatum dient als Vorschlag für die Eröffnungsprämie
-- (per "Echte Ausführungskurse"-Override überschreibbar).
--
-- Muster: get_option_data_at_date / get_option_date_range aus spreads_backtesting.py
-- Quelle: "OptionDataMassiveHistory" (+ "OptionDataMassive" für CURRENT_DATE).
-- Params: :symbol, :entry_date, :dte_min, :dte_max
--   :dte_min/:dte_max filtern auf die Restlaufzeit AM Einstiegsdatum
--   (expiration_date - entry_date), sodass nur Puts im gewählten DTE-Bereich erscheinen.
--
-- Hinweis: day_close ist die Prämie je Aktie ($). shares_per_contract i.d.R. 100.
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
            AND contract_type = 'put'
    UNION ALL
        SELECT CURRENT_DATE AS date, * FROM "OptionDataMassive"
        WHERE CAST(:entry_date AS date) = CURRENT_DATE
            AND symbol = :symbol
            AND contract_type = 'put'
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
ORDER BY a.expiration_date ASC, a.strike_price DESC
