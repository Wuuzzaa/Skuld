SELECT DISTINCT
    company_sector AS Sector
FROM
    "FundamentalData"
WHERE
    company_sector IS NOT NULL
ORDER BY
    company_sector;