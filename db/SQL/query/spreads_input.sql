SELECT
    symbol,
    expiration_date,
    "option-type",
    strike,
    ask,
    bid,
    (ask + bid) / 2 as mid,
    delta,
    iv,
    theta,
    close,
    earnings_date,
    days_to_expiration,
    days_to_ernings,
    spread,
    spread_ptc
FROM
    OptionDataMerged
WHERE
    expiration_date =:expiration_date;