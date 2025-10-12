SELECT DISTINCT
    expiration_date,
    days_to_expiration
FROM
    OptionDataMerged
ORDER BY
    days_to_expiration;