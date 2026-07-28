SELECT
    expiration_date,
    days_to_expiration,
    COUNT(DISTINCT symbol) AS symbol_count
FROM
    "OptionData" AS a
WHERE
    days_to_expiration > 0
    AND expiration_date > CURRENT_DATE
GROUP BY
    expiration_date, days_to_expiration
ORDER BY
    expiration_date;