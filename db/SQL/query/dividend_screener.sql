-- Zahltagstrategie Dividend Screener
-- Pulls all data needed for the 11-point scoring matrix from StockData view
-- Scoring: 5 Fundamental + 5 Dividend + 1 Technical = max 33 points
SELECT
    s.symbol,
    s.company_name,
    s.company_sector AS sector,
    s.company_industry AS industry,
    s.company_country AS country,
    ROUND(s.live_stock_price::numeric, 2) AS price,

    -- Fundamental metrics (5 criteria)
    ROUND(s."Summary_trailingPE"::numeric, 2) AS trailing_pe,
    ROUND(s."KeyStats_forwardPE"::numeric, 2) AS forward_pe,
    ROUND(s."FinData_profitMargins"::numeric * 100, 2) AS profit_margin_pct,
    ROUND(s."FinData_operatingMargins"::numeric * 100, 2) AS operating_margin_pct,
    ROUND(s."KeyStats_trailingEps"::numeric, 2) AS trailing_eps,
    ROUND(s."KeyStats_forwardEps"::numeric, 2) AS forward_eps,
    ROUND(s."Forward_EPS_Growth_Percent"::numeric, 2) AS eps_growth_pct,
    ROUND(s."FinData_debtToEquity"::numeric, 2) AS debt_to_equity,
    ROUND(s."FinData_returnOnEquity"::numeric * 100, 2) AS roe_pct,
    ROUND(s."FinData_currentRatio"::numeric, 2) AS current_ratio,
    ROUND(s."KeyStats_priceToBook"::numeric, 2) AS price_to_book,
    ROUND(s."Summary_marketCap"::numeric / 1000000000.0, 2) AS market_cap_b,

    -- Dividend metrics (5 criteria)
    ROUND(s."Summary_dividendYield"::numeric * 100, 2) AS dividend_yield_pct,
    ROUND(s."Summary_trailingAnnualDividendRate"::numeric, 4) AS annual_dividend_rate,
    ROUND(s."Summary_payoutRatio"::numeric * 100, 2) AS payout_ratio_pct,
    s.dividend_growth_years,
    s.dividend_classification,
    s.no_dividend_payouts_last_year AS dividend_payments_per_year,
    ROUND(s."Summary_fiveYearAvgDividendYield"::numeric, 2) AS five_year_avg_yield,

    -- Technical indicator (1 criterion)
    ROUND(s."RSI_14"::numeric, 2) AS rsi_14,
    ROUND(s."MACD_12_26_9"::numeric, 4) AS macd,
    ROUND(s."MACDh_12_26_9"::numeric, 4) AS macd_histogram,
    ROUND(s."SMA_50"::numeric, 2) AS sma_50,
    ROUND(s."SMA_200"::numeric, 2) AS sma_200,

    -- Additional screening fields
    ROUND(s."Summary_averageVolume"::numeric, 0) AS avg_volume,
    ROUND(s."Summary_fiftyTwoWeekLow"::numeric, 2) AS week_52_low,
    ROUND(s."Summary_fiftyTwoWeekHigh"::numeric, 2) AS week_52_high,
    ROUND(s."KeyStats_shortPercentOfFloat"::numeric * 100, 2) AS short_pct_float,
    s."FinData_recommendationMean" AS analyst_recommendation,
    s."FinData_numberOfAnalystOpinions" AS analyst_count,
    s."Summary_beta" AS beta,

    -- Calculated convenience fields
    CASE
        WHEN s."SMA_200" IS NOT NULL AND s."SMA_200" > 0
        THEN ROUND(((s.live_stock_price - s."SMA_200") / s."SMA_200" * 100)::numeric, 2)
        ELSE NULL
    END AS pct_from_sma200,
    CASE
        WHEN s."Summary_fiftyTwoWeekHigh" IS NOT NULL AND s."Summary_fiftyTwoWeekHigh" > 0
        THEN ROUND(((s.live_stock_price - s."Summary_fiftyTwoWeekHigh") / s."Summary_fiftyTwoWeekHigh" * 100)::numeric, 2)
        ELSE NULL
    END AS pct_from_52w_high

FROM "StockData" s
WHERE
    s.live_stock_price IS NOT NULL
    AND s.live_stock_price > 0
    AND s."Summary_dividendYield" IS NOT NULL
    AND s."Summary_dividendYield" > 0
    AND s.company_sector IS NOT NULL
ORDER BY s.symbol;
