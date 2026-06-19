-- Earnings Put Scanner
-- Candidate scan: one row per symbol with upcoming earnings.
-- Expected Move is calculated from the ATM put closest to earnings date
-- using: stock_price × IV × sqrt(DTE / 365)
-- Stock price from StockData.FinData_currentPrice (reliable daily update)

WITH atm_iv AS (
    -- For each symbol: pick the single ATM put with DTE closest to earnings
    SELECT DISTINCT ON (o.symbol)
        o.symbol,
        o.implied_volatility   AS atm_iv,
        o.days_to_expiration   AS atm_dte
    FROM "OptionDataMerged" o
    JOIN "StockData" s ON s.symbol = o.symbol
    WHERE
        o.contract_type = 'put'
        AND o.days_to_expiration BETWEEN 1 AND 45
        AND o.implied_volatility > 0
        AND o.open_interest > 10
    ORDER BY
        o.symbol,
        ABS(o.strike_price - s."FinData_currentPrice") ASC,  -- closest to ATM
        o.days_to_expiration ASC                              -- shortest expiry
)
SELECT DISTINCT ON (o.symbol)
    o.symbol,
    o.earnings_date,
    o.days_to_earnings,
    s."FinData_currentPrice"                                        AS live_stock_price,
    ROUND((
        s."FinData_currentPrice"
        * a.atm_iv
        * sqrt(GREATEST(a.atm_dte, 1)::numeric / 365.0)
    )::numeric, 2)                                                  AS expected_move,
    ROUND((
        a.atm_iv
        * sqrt(GREATEST(a.atm_dte, 1)::numeric / 365.0)
        * 100
    )::numeric, 1)                                                  AS expected_move_pct,
    o.iv_rank,
    o.iv_percentile,
    o.historical_volatility_30d,
    o."Summary_marketCap"                                           AS market_cap,
    o."Summary_trailingPE"                                          AS trailing_pe,
    o."Summary_averageVolume"                                       AS avg_volume,
    o.dividend_classification,
    o."KeyStats_profitMargins"                                      AS profit_margin
FROM "OptionDataMerged" o
JOIN "StockData"  s ON s.symbol = o.symbol
JOIN atm_iv       a ON a.symbol = o.symbol
WHERE
    o.days_to_earnings BETWEEN 0 AND :days_ahead
    AND o."Summary_marketCap" > 2000000000
    AND s."FinData_currentPrice" BETWEEN 15 AND 250
ORDER BY o.symbol, o.days_to_earnings ASC
