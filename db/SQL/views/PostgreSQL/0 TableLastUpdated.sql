CREATE
OR REPLACE VIEW "TableLastUpdated" AS
SELECT
    table_name,
    MAX(timestamp) AS last_updated
FROM
    "DataChangeLogs" AS logs
WHERE
    operation_type IN ('UPSERT', 'UPDATE', 'INSERT')
    AND timestamp >= CURRENT_DATE - INTERVAL '4 days' -- consider changes in the last 4 days
    AND timestamp <= CURRENT_DATE -- consider changes up to the current date
GROUP BY
    table_name