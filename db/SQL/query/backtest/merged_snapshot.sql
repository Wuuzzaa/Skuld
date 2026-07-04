-- Backtest merged snapshot for a specific target_date.
--
-- Note: This is a template. The columns and WHERE clause are
-- injected dynamically by src/backtesting/data/loader.py.
-- Kept in this directory per backtest.md Kap. 13.1: "Alle SQL-Queries
-- müssen in Skuld/db/SQL/query/backtest abgelegt werden".
--
-- Parameters:
--   :target_date  — the EOD snapshot date to reconstruct
SELECT {columns}
FROM "getOptionDataMergedHistory"(:target_date)
{where_clause};
