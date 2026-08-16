-- Tab 2a: IV vs. Realized Volatility (IV/HV Ratio)
-- HV Rank / HV Percentile are computed in Python (pandas) to avoid SQL log-return issues
WITH
current_data AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        company_name,
        implied_volatility        AS imp_vol,
        historical_volatility_30d AS hv_30d,
        iv_rank,
        iv_percentile,
        earnings_date
    FROM "OptionDataMerged"
    WHERE implied_volatility IS NOT NULL AND implied_volatility > 0
      AND historical_volatility_30d IS NOT NULL AND historical_volatility_30d > 0
    ORDER BY symbol, implied_volatility DESC
),
yesterday_iv AS (
    SELECT symbol, iv AS iv_yesterday
    FROM "StockImpliedVolatilityMassiveHistoryDaily"
    WHERE snapshot_date = (
        SELECT MAX(snapshot_date)
        FROM "StockImpliedVolatilityMassiveHistoryDaily"
        WHERE snapshot_date < CURRENT_DATE
    )
)
SELECT
    c.symbol,
    c.company_name                                                         AS name,
    c.imp_vol,
    CASE WHEN y.iv_yesterday IS NOT NULL AND y.iv_yesterday > 0
         THEN c.imp_vol - y.iv_yesterday ELSE NULL END                     AS iv_chg,
    c.hv_30d,
    CASE WHEN c.hv_30d > 0 THEN c.imp_vol / c.hv_30d ELSE NULL END        AS iv_hv_ratio,
    c.iv_rank,
    c.iv_percentile,
    c.earnings_date
FROM current_data c
LEFT JOIN yesterday_iv y ON c.symbol = y.symbol
ORDER BY iv_hv_ratio DESC NULLS LAST;
