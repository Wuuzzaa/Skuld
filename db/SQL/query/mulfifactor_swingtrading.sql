SELECT Distinct
    symbol,
    KeyStats_priceToBook AS 'price_to_book',
    Summary_trailingPE AS 'price_to_earnings',
    Summary_priceToSalesTrailing12Months AS 'price_to_sales',
    EBITDA / EnterpriseValue AS 'ebitda_to_enterprise_value',
    FinData_currentPrice / FinData_freeCashflow AS 'price_to_cashflow',
    KeyStats_52WeekChange + Summary_trailingAnnualDividendYield AS '1_year_shareholder_yield'
FROM
    FundamentalDataYahoo
WHERE
    Summary_marketCap > 200000000;