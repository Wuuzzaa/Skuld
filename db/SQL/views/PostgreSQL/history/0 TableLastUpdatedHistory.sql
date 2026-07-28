CREATE
OR REPLACE VIEW "TableLastUpdatedHistory" AS
SELECT
    DATE(timestamp) AS date,
    table_name,
    MAX(timestamp) AS last_updated
FROM
    "DataChangeLogs"
WHERE
    operation_type IN ('UPSERT', 'UPDATE', 'INSERT')
GROUP BY
    DATE(timestamp),
    table_name