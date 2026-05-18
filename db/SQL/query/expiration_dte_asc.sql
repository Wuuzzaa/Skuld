SELECT
    expiration_date,
    days_to_expiration,
    COUNT(DISTINCT symbol) AS symbol_count
FROM
    "OptionData"
WHERE
    days_to_expiration > 0
GROUP BY
    expiration_date, days_to_expiration
ORDER BY
    days_to_expiration;