SELECT
    *
FROM
    OptionDataTradingView
WHERE
    option_osi NOT IN (
        SELECT
            option_osi
        FROM
            OptionData
    )
ORDER BY
    expiration_date, "option-type", strike;

SELECT
    *
FROM
    OptionDataYahoo
WHERE
    contractSymbol NOT IN (
        SELECT
            contractSymbol
        FROM
            OptionData
    )
    --AND contractSymbol = 'AAPL250905C00150000'
ORDER BY
    expiration_date, "option-type", strike;

SELECT
    COUNT(*)
FROM
    OptionDataYahoo

SELECT
    COUNT(*)
FROM
    OptionData

SELECT
    *
FROM
    OptionDataTradingView
WHERE
    option_osi = 'AAPL251121C00135000';

SELECT
    *
FROM
    OptionDataTradingView
WHERE
    expiration_date = 20251121;

SELECT
    *
FROM
    OptionData
WHERE
    option_osi = 'AAPL250905C00150000'