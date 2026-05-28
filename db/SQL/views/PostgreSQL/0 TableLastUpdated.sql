CREATE
OR REPLACE VIEW "TableLastUpdated" AS
SELECT
    table_name,
    MAX(timestamp) AS last_updated
FROM
    "DataChangeLogs"
WHERE
    operation_type IN ('UPSERT', 'UPDATE', 'INSERT')
GROUP BY
    table_name