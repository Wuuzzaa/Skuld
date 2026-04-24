SELECT DISTINCT
    symbol,
    company_name AS "Company",
    company_sector AS "Sector",
    company_industry AS "Industry",
    live_stock_price                                                            AS price,
    "KeyStats_priceToBook"                                                      AS price_to_book,
    "Summary_trailingPE"                                                        AS price_to_earnings,
    "Summary_priceToSalesTrailing12Months"                                      AS price_to_sales,
    "EBITDA" / NULLIF("EnterpriseValue", 0)                                     AS ebitda_to_enterprise_value,
    LIVE_STOCK_PRICE / NULLIF(("FreeCashFlow" / NULLIF("KeyStats_sharesOutstanding", 0)), 0) AS price_to_cashflow,
    "Summary_trailingAnnualDividendYield"                                       AS shareholder_yield,
    "KeyStats_52WeekChange"                                                     AS "1_year_price_appreciation",
    "BasicEPS",
    "DilutedEPS",
    "Forward_EPS_Growth_Percent",
    "KeyStats_trailingEps",
    "KeyStats_forwardEps"
FROM
    "OptionDataMerged"
WHERE
    "Summary_marketCap" > 200000000;
