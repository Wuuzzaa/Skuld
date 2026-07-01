-- Overall date coverage of the historized option data.
-- Used by the Validator to bound user-requested backtest date ranges.
SELECT
    MIN("date") AS min_date,
    MAX("date") AS max_date,
    COUNT(DISTINCT "date") AS trading_days
FROM "OptionDataMassiveHistoryDaily";
