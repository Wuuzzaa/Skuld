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
    spread_ptc,
    iv_rank,
    iv_percentile,
    option_open_interest
FROM
    OptionDataMerged
WHERE
    expiration_date =:expiration_date;