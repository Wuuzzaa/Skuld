SELECT DISTINCT
    company_industry AS Industry
FROM
    "FundamentalData"
WHERE
    company_industry IS NOT NULL
ORDER BY
    company_industry;