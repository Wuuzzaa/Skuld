SELECT DISTINCT
    symbol,
    "KeyStats_priceToBook"                                                      AS price_to_book,
    "Summary_trailingPE"                                                        AS price_to_earnings,
    "Summary_priceToSalesTrailing12Months"                                      AS price_to_sales,
    "EBITDA" / "EnterpriseValue"                                                AS ebitda_to_enterprise_value,
    "FinData_currentPrice" / ("FreeCashFlow" / "KeyStats_sharesOutstanding")    AS price_to_cashflow,
    "Summary_trailingAnnualDividendYield"                                       AS shareholder_yield,
    "KeyStats_52WeekChange"                                                     AS "1_year_price_appreciation"
FROM
    "FundamentalDataYahoo"
WHERE
    "Summary_marketCap" > 200000000;