-- Distinct symbols available on a given target_date. Used by the frontend
-- to populate the static-universe symbol picker.
--
-- Parameters:
--   :target_date  — the EOD snapshot date to check
SELECT DISTINCT symbol
FROM "getOptionDataMergedHistory"(:target_date)
ORDER BY symbol;
