-- Tab 2b: Rising / Falling Volatility
-- Criteria for Rising: IV increasing, 5D-avg IV >= 1.05 * 1M-avg IV, IV/HV > 1.05
-- Criteria for Falling: IV decreasing, 5D-avg IV <= 0.95 * 1M-avg IV
WITH
iv_history AS (
    SELECT
        symbol,
        snapshot_date,
        iv
    FROM "StockImpliedVolatilityMassiveHistoryDaily"
    WHERE snapshot_date >= CURRENT_DATE - INTERVAL '35 days'
),
iv_avgs AS (
    SELECT
        symbol,
        -- 5-day average IV
        AVG(iv) FILTER (WHERE snapshot_date >= CURRENT_DATE - INTERVAL '5 days')  AS iv_5d_avg,
        -- 1-month average IV (21 trading days)
        AVG(iv) FILTER (WHERE snapshot_date >= CURRENT_DATE - INTERVAL '21 days') AS iv_1m_avg
    FROM iv_history
    GROUP BY symbol
),
yesterday_iv AS (
    SELECT symbol, iv AS iv_yesterday
    FROM "StockImpliedVolatilityMassiveHistoryDaily"
    WHERE snapshot_date = (
        SELECT MAX(snapshot_date)
        FROM "StockImpliedVolatilityMassiveHistoryDaily"
        WHERE snapshot_date < CURRENT_DATE
    )
),
current_data AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        company_name,
        implied_volatility     AS imp_vol,
        historical_volatility_30d AS hv_30d,
        iv_rank,
        iv_percentile,
        earnings_date,
        total_options_vol AS total_options_volume
    FROM "OptionDataMerged"
    WHERE implied_volatility IS NOT NULL AND implied_volatility > 0
      AND historical_volatility_30d IS NOT NULL AND historical_volatility_30d > 0
    ORDER BY symbol, implied_volatility DESC
)
SELECT
    c.symbol,
    c.company_name                                                              AS name,
    c.imp_vol,
    CASE WHEN y.iv_yesterday IS NOT NULL AND y.iv_yesterday > 0
         THEN c.imp_vol - y.iv_yesterday ELSE NULL END                          AS iv_chg,
    -- 5D/1M IV ratio as percentage (e.g. 107% means 5D avg is 7% above 1M avg)
    CASE WHEN a.iv_1m_avg > 0
         THEN a.iv_5d_avg / a.iv_1m_avg * 100 ELSE NULL END                    AS iv_5d_1m_pct,
    CASE WHEN c.hv_30d > 0 THEN c.imp_vol / c.hv_30d ELSE NULL END             AS iv_hv_ratio,
    c.iv_rank,
    c.iv_percentile,
    c.earnings_date,
    c.total_options_volume,
    -- direction flag for Python-side filtering
    CASE WHEN c.imp_vol > COALESCE(y.iv_yesterday, c.imp_vol) THEN 'rising'
         WHEN c.imp_vol < COALESCE(y.iv_yesterday, c.imp_vol) THEN 'falling'
         ELSE 'flat' END                                                        AS iv_direction
FROM current_data c
LEFT JOIN yesterday_iv y ON c.symbol = y.symbol
LEFT JOIN iv_avgs a      ON c.symbol = a.symbol
WHERE a.iv_5d_avg IS NOT NULL
  AND a.iv_1m_avg IS NOT NULL
  AND a.iv_1m_avg > 0
ORDER BY iv_5d_1m_pct DESC NULLS LAST;
