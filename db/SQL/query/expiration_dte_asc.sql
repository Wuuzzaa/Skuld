SELECT DISTINCT
    expiration_date,
    days_to_expiration
FROM
    "OptionData" AS a
WHERE
    expiration_date > CURRENT_DATE
ORDER BY
    expiration_date;