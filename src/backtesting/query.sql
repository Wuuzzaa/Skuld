INSERT INTO
    OptionDataYahoo_History (
        symbol,
        expiration_date,
        option - type,
        contractSymbol,
        strike,
        currency,
        lastPrice,
        change,
        percentChange,
        option_open_interest,
        bid,
        ask,
        contractSize,
        lastTradeDate,
        impliedVolatility,
        inTheMoney,
        option_volume,
        snapshot_date
    )
SELECT DISTINCT
    symbol,
    expiration_date,
    option - type,
    contractSymbol,
    strike,
    currency,
    lastPrice,
    change,
    percentChange,
    option_open_interest,
    bid,
    ask,
    contractSize,
    lastTradeDate,
    impliedVolatility,
    inTheMoney,
    option_volume,
    DATE ('now')
FROM
    OptionDataYahoo
WHERE
    (symbol = 'A')