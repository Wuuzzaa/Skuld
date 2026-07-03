-- Overall date coverage of the historized option data.
-- Used by the Validator to bound user-requested backtest date ranges.
SELECT
    MIN("snapshot_date") AS min_date,
    MAX("snapshot_date") AS max_date,
    COUNT(DISTINCT "snapshot_date") AS trading_days
FROM "OptionDataMassiveHistoryDaily";
