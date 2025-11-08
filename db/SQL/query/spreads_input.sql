SELECT
    symbol,
    expiration_date,
    "option-type",
    strike,
    ask,
    bid,
    delta,
    iv,
    theta,
    close,
    earnings_date,
    days_to_expiration,
    days_to_ernings
FROM
    OptionDataMerged
WHERE
    expiration_date =:expiration_date;