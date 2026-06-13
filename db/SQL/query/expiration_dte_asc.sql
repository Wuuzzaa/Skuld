SELECT DISTINCT
    expiration_date,
    days_to_expiration
FROM
    "OptionData" AS a
WHERE
    days_to_expiration > 0
ORDER BY
    days_to_expiration;