-- Dividend Portfolio Builder - Candidates with Payment Cycle Classification
-- Determines which quarterly payment cycle each stock belongs to:
--   Cycle A: Pays in Jan/Apr/Jul/Oct
--   Cycle B: Pays in Feb/May/Aug/Nov
--   Cycle C: Pays in Mar/Jun/Sep/Dec
-- Most US dividend stocks pay quarterly; monthly payers get assigned to all cycles.

WITH dividend_months AS (
    -- Get the months in which each symbol paid dividends in the last 2 years
    SELECT
        symbol,
        EXTRACT(MONTH FROM snapshot_date)::int AS pay_month,
        COUNT(*) AS payments_in_month
    FROM "StockPricesYahooHistoryDaily"
    WHERE dividends > 0
      AND snapshot_date > CURRENT_DATE - INTERVAL '2 years'
    GROUP BY symbol, EXTRACT(MONTH FROM snapshot_date)::int
),
cycle_classification AS (
    -- Classify into payment cycle based on which months have the most payments
    SELECT
        symbol,
        -- Count payments in each cycle
        SUM(CASE WHEN pay_month IN (1,4,7,10) THEN payments_in_month ELSE 0 END) AS cycle_a_count,
        SUM(CASE WHEN pay_month IN (2,5,8,11) THEN payments_in_month ELSE 0 END) AS cycle_b_count,
        SUM(CASE WHEN pay_month IN (3,6,9,12) THEN payments_in_month ELSE 0 END) AS cycle_c_count,
        SUM(payments_in_month) AS total_payments
    FROM dividend_months
    GROUP BY symbol
),
classified AS (
    SELECT
        symbol,
        cycle_a_count,
        cycle_b_count,
        cycle_c_count,
        total_payments,
        CASE
            -- Monthly payers (12 payments/year = pays in all months)
            WHEN total_payments >= 20 THEN 'MONTHLY'
            -- Quarterly: pick dominant cycle
            WHEN cycle_a_count >= cycle_b_count AND cycle_a_count >= cycle_c_count THEN 'A'
            WHEN cycle_b_count >= cycle_a_count AND cycle_b_count >= cycle_c_count THEN 'B'
            ELSE 'C'
        END AS payment_cycle
    FROM cycle_classification
    WHERE total_payments >= 2  -- At least 2 payments in 2 years to be considered
)
-- Join with screener data
SELECT
    s.symbol,
    s.company_name,
    s.company_sector AS sector,
    s.company_industry AS industry,
    ROUND(s.live_stock_price::numeric, 2) AS price,
    ROUND(s."Summary_dividendYield"::numeric * 100, 2) AS dividend_yield_pct,
    ROUND(s."Summary_trailingAnnualDividendRate"::numeric, 4) AS annual_dividend_rate,
    s.dividend_growth_years,
    s.dividend_classification,
    ROUND(s."Summary_payoutRatio"::numeric * 100, 2) AS payout_ratio_pct,
    ROUND(s."Summary_trailingPE"::numeric, 2) AS trailing_pe,
    ROUND(s."FinData_profitMargins"::numeric * 100, 2) AS profit_margin_pct,
    ROUND(s."Forward_EPS_Growth_Percent"::numeric, 2) AS eps_growth_pct,
    ROUND(s."FinData_debtToEquity"::numeric, 2) AS debt_to_equity,
    ROUND(s."FinData_returnOnEquity"::numeric * 100, 2) AS roe_pct,
    ROUND(s."Summary_marketCap"::numeric / 1000000000.0, 2) AS market_cap_b,
    ROUND(s."Summary_averageVolume"::numeric, 0) AS avg_volume,
    ROUND(s."RSI_14"::numeric, 2) AS rsi_14,
    ROUND(s."MACD_12_26_9"::numeric, 4) AS macd,
    ROUND(s."MACDh_12_26_9"::numeric, 4) AS macd_histogram,
    ROUND(s."SMA_200"::numeric, 2) AS sma_200,
    ROUND(s."Summary_fiveYearAvgDividendYield"::numeric, 2) AS five_year_avg_yield,
    CASE
        WHEN s."SMA_200" IS NOT NULL AND s."SMA_200" > 0
        THEN ROUND(((s.live_stock_price - s."SMA_200") / s."SMA_200" * 100)::numeric, 2)
        ELSE NULL
    END AS pct_from_sma200,
    -- Payment cycle info
    c.payment_cycle,
    c.total_payments AS payments_last_2y
FROM "StockData" s
INNER JOIN classified c ON s.symbol = c.symbol
WHERE
    s.live_stock_price IS NOT NULL
    AND s.live_stock_price > 0
    AND s."Summary_dividendYield" IS NOT NULL
    AND s."Summary_dividendYield" > 0.02  -- Min 2% yield for portfolio candidates
    AND s."Summary_trailingAnnualDividendRate" IS NOT NULL
    AND s."Summary_trailingAnnualDividendRate" > 0
    AND s.company_sector IS NOT NULL
ORDER BY s.symbol;
