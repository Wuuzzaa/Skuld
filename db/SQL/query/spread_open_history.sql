-- spread_open_history.sql
-- Historische Optionskette (PUTS und CALLS) eines Symbols für EINEN Verfall,
-- zu einem gewählten Einstiegsdatum. Für die Time-Travel-Funktion im Spread-Roller:
-- der User wählt den Tag, an dem er den Spread eröffnet hat, und day_close an
-- diesem Tag dient als Vorschlag für den Eröffnungs-Credit/-Debit der beiden Beine
-- (per number_input überschreibbar).
--
-- Muster: roll_put_history.sql (get_option_data_at_date / spreads_backtesting.py).
-- Quelle: "OptionDataMassiveHistory" (+ "OptionDataMassive" für CURRENT_DATE).
-- Anders als roll_put_history.sql: KEIN harter contract_type = 'put' — Debit-Spreads
-- (Bull-Call/Bear-Put) nutzen Calls, daher werden beide Seiten geliefert.
-- Params: :symbol, :entry_date, :expiration_date
--   Nur der eine Verfall der bestehenden Position, beide Beine liegen darauf.
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
    b.close AS stock_close
FROM (
        SELECT * FROM "OptionDataMassiveHistory"
        WHERE date = CAST(:entry_date AS date)
            AND symbol = :symbol
    UNION ALL
        SELECT CURRENT_DATE AS date, * FROM "OptionDataMassive"
        WHERE CAST(:entry_date AS date) = CURRENT_DATE
            AND symbol = :symbol
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
  AND a.expiration_date = :expiration_date
ORDER BY a.contract_type ASC, a.strike_price ASC
