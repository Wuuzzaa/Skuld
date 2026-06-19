-- Earnings Put Scanner
-- Expected Move = ATM Straddle (Call + Put, shortest weekly expiry AFTER earnings)
-- Stock price from StockData.FinData_currentPrice

SELECT
    c.symbol,
    c.earnings_date,
    c.days_to_earnings,
    ROUND(s."FinData_currentPrice"::numeric, 2)                          AS live_stock_price,
    oc.expiration_date                                                    AS straddle_expiry,
    oc.strike_price                                                       AS atm_strike,
    ROUND((oc.premium_option_price + op.premium_option_price)::numeric, 2) AS expected_move,
    ROUND(
        ((oc.premium_option_price + op.premium_option_price)
        / s."FinData_currentPrice" * 100)::numeric, 1
    )                                                                     AS expected_move_pct,
    c.iv_rank,
    c.iv_percentile,
    c.historical_volatility_30d,
    c.market_cap,
    c.trailing_pe,
    c.avg_volume,
    c.dividend_classification,
    c.profit_margin
FROM (
    -- One row per symbol: earnings metadata
    SELECT DISTINCT ON (o.symbol)
        o.symbol,
        o.earnings_date,
        o.days_to_earnings,
        o.iv_rank,
        o.iv_percentile,
        o.historical_volatility_30d,
        o."Summary_marketCap"        AS market_cap,
        o."Summary_trailingPE"       AS trailing_pe,
        o."Summary_averageVolume"    AS avg_volume,
        o.dividend_classification,
        o."KeyStats_profitMargins"   AS profit_margin
    FROM "OptionDataMerged" o
    WHERE o.days_to_earnings BETWEEN 0 AND :days_ahead
    ORDER BY o.symbol, o.days_to_earnings ASC
) c
JOIN "StockData" s
    ON s.symbol = c.symbol
   AND s."FinData_currentPrice" BETWEEN 15 AND 250
   AND c.market_cap > 2000000000
-- ATM call: shortest expiry after earnings, strike closest to stock price
JOIN LATERAL (
    SELECT o2.expiration_date, o2.strike_price, o2.premium_option_price
    FROM "OptionDataMerged" o2
    WHERE o2.symbol = c.symbol
      AND o2.contract_type = 'call'
      AND o2.expiration_date > c.earnings_date::date
      AND o2.days_to_expiration BETWEEN 1 AND 14
      AND o2.open_interest > 10
      AND o2.premium_option_price > 0
    ORDER BY o2.expiration_date ASC, ABS(o2.strike_price - s."FinData_currentPrice") ASC
    LIMIT 1
) oc ON true
-- Matching put: same expiry and strike
JOIN LATERAL (
    SELECT o3.premium_option_price
    FROM "OptionDataMerged" o3
    WHERE o3.symbol = c.symbol
      AND o3.contract_type = 'put'
      AND o3.expiration_date = oc.expiration_date
      AND o3.strike_price = oc.strike_price
      AND o3.open_interest > 10
      AND o3.premium_option_price > 0
    LIMIT 1
) op ON true
ORDER BY c.days_to_earnings ASC, c.symbol ASC
