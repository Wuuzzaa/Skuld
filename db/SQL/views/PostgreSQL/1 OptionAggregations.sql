DROP VIEW IF EXISTS "OptionAggregations" CASCADE;
CREATE VIEW
    "OptionAggregations" AS
SELECT
    symbol,
    SUM(a.day_volume) AS total_day_volume,
    CASE WHEN SUM(CASE WHEN a.contract_type = 'call' THEN a.day_volume ELSE 0 END) > 0 THEN
        SUM(CASE WHEN a.contract_type = 'call' THEN a.day_volume ELSE 0 END) * 100.0 / SUM(a.day_volume)
    ELSE 0 END AS call_volume_pct
FROM "OptionDataMassive" AS a
WHERE a.day_volume > 0
GROUP BY symbol