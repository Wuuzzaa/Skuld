SELECT DISTINCT
    expiration_date,
    days_to_expiration
FROM
    OptionData
WHERE
    days_to_expiration is not null -- todo db scheme anpassen nur massive api optionsdaten. inkl. der berechneten Felder wie dte.
ORDER BY
    days_to_expiration;