SELECT DISTINCT
    expiration_date,
    days_to_expiration
FROM
    OptionData
ORDER BY
    days_to_expiration;