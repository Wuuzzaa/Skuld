-- Tab 2a: IV vs. Realized Volatility (IV/HV Ratio)
-- Includes HV Rank and HV Percentile from 1-year historical HV data
WITH
current_data AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        company_name,
        implied_volatility     AS imp_vol,
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
),
-- Step 1: compute log returns
log_returns AS (
    SELECT
        symbol,
        date,
        LN(adjclose / NULLIF(LAG(adjclose) OVER (PARTITION BY symbol ORDER BY date), 0)) AS log_return
    FROM (
        SELECT symbol, snapshot_date AS date, adjclose
        FROM "StockPricesYahooHistoryDaily"
        WHERE snapshot_date >= CURRENT_DATE - INTERVAL '13 months'
        UNION ALL
        SELECT symbol, CURRENT_DATE AS date, adjclose
        FROM "StockPricesYahoo"
    ) prices
),
-- Step 2: rolling 30d HV per day
hv_history AS (
    SELECT
        symbol,
        date,
        STDDEV(log_return) OVER (
            PARTITION BY symbol
            ORDER BY date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) * SQRT(252) AS hv_30d_hist
    FROM log_returns
    WHERE log_return IS NOT NULL
),
-- Step 3: most recent HV value per symbol (no nested window)
hv_latest AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        hv_30d_hist AS hv_current
    FROM hv_history
    WHERE hv_30d_hist IS NOT NULL
    ORDER BY symbol, date DESC
),
-- Step 4: aggregate stats per symbol
hv_agg AS (
    SELECT
        h.symbol,
        l.hv_current,
        MAX(h.hv_30d_hist)                                              AS hv_high,
        MIN(h.hv_30d_hist)                                              AS hv_low,
        COUNT(*)                                                        AS hv_days,
        SUM(CASE WHEN h.hv_30d_hist < l.hv_current THEN 1 ELSE 0 END) AS hv_days_lower
    FROM hv_history h
    JOIN hv_latest l ON h.symbol = l.symbol
    WHERE h.hv_30d_hist IS NOT NULL
    GROUP BY h.symbol, l.hv_current
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
    CASE WHEN (h.hv_high - h.hv_low) > 0
         THEN (h.hv_current - h.hv_low) / (h.hv_high - h.hv_low) * 100
         ELSE 0 END                                                        AS hv_rank,
    CASE WHEN h.hv_days > 0
         THEN h.hv_days_lower::float / h.hv_days * 100
         ELSE NULL END                                                     AS hv_percentile,
    c.earnings_date
FROM current_data c
LEFT JOIN yesterday_iv y ON c.symbol = y.symbol
LEFT JOIN hv_agg h       ON c.symbol = h.symbol
ORDER BY iv_hv_ratio DESC NULLS LAST;

WITH
current_data AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        company_name,
        implied_volatility     AS imp_vol,
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
),
-- HV history for HV Rank / HV Percentile
hv_history AS (
    SELECT
        symbol,
        STDDEV(log_return) OVER (
            PARTITION BY symbol
            ORDER BY date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) * SQRT(252) AS hv_30d_hist,
        date
    FROM (
        SELECT
            symbol,
            date,
            LN(adjclose / NULLIF(LAG(adjclose) OVER (PARTITION BY symbol ORDER BY date), 0)) AS log_return
        FROM (
            SELECT symbol, snapshot_date AS date, adjclose
            FROM "StockPricesYahooHistoryDaily"
            WHERE snapshot_date >= CURRENT_DATE - INTERVAL '13 months'
            UNION ALL
            SELECT symbol, CURRENT_DATE AS date, adjclose
            FROM "StockPricesYahoo"
        ) prices
    ) returns
),
hv_stats AS (
    SELECT
        symbol,
        -- last known HV (most recent date)
        FIRST_VALUE(hv_30d_hist) OVER (
            PARTITION BY symbol ORDER BY date DESC
        ) AS hv_current,
        MAX(hv_30d_hist) OVER (PARTITION BY symbol) AS hv_high,
        MIN(hv_30d_hist) OVER (PARTITION BY symbol) AS hv_low,
        COUNT(*) OVER (PARTITION BY symbol) AS hv_days,
        SUM(CASE WHEN hv_30d_hist < FIRST_VALUE(hv_30d_hist) OVER (PARTITION BY symbol ORDER BY date DESC)
                 THEN 1 ELSE 0 END) OVER (PARTITION BY symbol) AS hv_days_lower
    FROM hv_history
    WHERE hv_30d_hist IS NOT NULL
),
hv_agg AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        hv_current,
        CASE WHEN (hv_high - hv_low) > 0
             THEN (hv_current - hv_low) / (hv_high - hv_low) * 100
             ELSE 0 END AS hv_rank,
        CASE WHEN hv_days > 0
             THEN hv_days_lower::float / hv_days * 100
             ELSE NULL END AS hv_percentile
    FROM hv_stats
    ORDER BY symbol
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
    h.hv_rank,
    h.hv_percentile,
    c.earnings_date
FROM current_data c
LEFT JOIN yesterday_iv y ON c.symbol = y.symbol
LEFT JOIN hv_agg h       ON c.symbol = h.symbol
ORDER BY iv_hv_ratio DESC NULLS LAST;
