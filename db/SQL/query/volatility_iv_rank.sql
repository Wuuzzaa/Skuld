-- Tab 1: IV Rank & IV Percentile Overview
WITH
current_iv_stats AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        iv_rank,
        iv_percentile,
        implied_volatility AS imp_vol,
        historical_volatility_30d AS hv_30d,
        earnings_date,
        company_name,
        total_day_volume,
        put_volume_pct
    FROM "OptionDataMerged"
    WHERE iv_rank IS NOT NULL
      AND iv_percentile IS NOT NULL
      AND implied_volatility IS NOT NULL
      AND implied_volatility > 0
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
    c.company_name                                                    AS name,
    c.imp_vol,
    CASE
        WHEN y.iv_yesterday IS NOT NULL AND y.iv_yesterday > 0
        THEN c.imp_vol - y.iv_yesterday
        ELSE NULL
    END                                                               AS iv_chg,
    c.hv_30d,
    CASE WHEN c.hv_30d > 0 THEN c.imp_vol / c.hv_30d ELSE NULL END   AS iv_hv_ratio,
    c.iv_rank,
    c.iv_percentile,
    c.total_day_volume,
    c.put_volume_pct,
    c.earnings_date
FROM current_iv_stats c
LEFT JOIN yesterday_iv y ON c.symbol = y.symbol
ORDER BY c.iv_rank DESC NULLS LAST;
