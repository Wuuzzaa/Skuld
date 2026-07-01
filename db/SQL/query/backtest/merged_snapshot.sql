-- Backtest merged snapshot for a specific target_date.
--
-- Consumed by src/backtesting/data/loader.py:SmartPreloader as an alternative
-- to calling `getOptionDataMergedHistory(date)` directly. Kept in this
-- directory per backtest.md Kap. 13.1: "Alle SQL-Queries müssen in
-- Skuld/db/SQL/query/backtest abgelegt werden".
--
-- Parameters:
--   :target_date  — the EOD snapshot date to reconstruct
SELECT *
FROM "getOptionDataMergedHistory"(:target_date);
