-- roll_symbols.sql
-- DISTINCT-Symbolliste für die Roller-Symbol-Selectbox (Autocomplete).
-- Nur Symbole, für die es überhaupt historische Optionsdaten gibt.
SELECT DISTINCT symbol
FROM "OptionDataMassiveHistory"
ORDER BY symbol
