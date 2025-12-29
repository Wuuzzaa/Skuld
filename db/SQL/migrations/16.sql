DROP TABLE IF EXISTS "DatesHistory";
Create Table "DatesHistory"(
    date DATE PRIMARY KEY,
    year INT,
    month INT,
    week INT
);

INSERT INTO "DatesHistory"
(date, year, month, week)
SELECT DISTINCT
snapshot_date as date,
strftime ('%Y', snapshot_date) as year,
strftime ('%m', snapshot_date) as month,
strftime ('%W', snapshot_date) as week
FROM "OptionDataYahooHistoryDaily"
where 1=1
ON CONFLICT (date) DO NOTHING;