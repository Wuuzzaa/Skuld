-- ITM Covered Call Scanner
-- Finds the optimal ITM call per symbol based on delta target proximity.
-- Metrics mirror the PowerOptions MorningUpdate newsletter:
--   Net Debit       = stock_price - premium
--   Assigned Return = (strike - net_debit) / net_debit
--   Annualized      = assigned_return / dte * 365
--   Downside Prot.  = (stock_price - net_debit) / stock_price
-- Stock price from StockData.FinData_currentPrice (reliable daily update).

WITH candidates AS (
    SELECT
        o.symbol,
        o.company_name,
        o.company_sector,
        s."FinData_currentPrice"                         AS stock_price,
        o.strike_price,
        o.premium_option_price                           AS premium,
        o.expiration_date,
        o.days_to_expiration                             AS dte,
        ABS(o.greeks_delta)                              AS delta,
        o.implied_volatility                             AS iv,
        o.open_interest,
        o.day_volume                                     AS volume,
        o.earnings_date,
        o.days_to_earnings,
        o.iv_rank,
        o.iv_percentile,
        o.historical_volatility_30d                      AS hv_30d,
        s."Summary_marketCap"                            AS market_cap,
        s."Summary_trailingPE"                           AS trailing_pe,
        s."Summary_averageVolume"                        AS avg_volume,
        -- Pick the call closest to delta target per symbol
        ROW_NUMBER() OVER (
            PARTITION BY o.symbol
            ORDER BY ABS(ABS(o.greeks_delta) - :delta_target) ASC,
                     o.days_to_expiration ASC
        ) AS delta_rank
    FROM "OptionDataMerged" o
    JOIN "StockData" s ON s.symbol = o.symbol
    WHERE
        o.contract_type       = 'call'
        AND o.strike_price    < s."FinData_currentPrice"   -- ITM only
        AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
        AND o.open_interest  >= :min_oi
        AND o.premium_option_price > 0
        AND s."FinData_currentPrice" BETWEEN 10 AND 500
        AND s."Summary_marketCap"   > :min_market_cap
        -- Exclude earnings during the holding period
        AND (o.days_to_earnings > o.days_to_expiration OR o.days_to_earnings IS NULL)
)
SELECT
    symbol,
    company_name,
    company_sector,
    ROUND(stock_price::numeric, 2)                                              AS stock_price,
    strike_price,
    ROUND(premium::numeric, 2)                                                  AS premium,
    expiration_date,
    dte,
    ROUND(delta::numeric, 3)                                                    AS delta,
    ROUND((iv * 100)::numeric, 1)                                                 AS iv_pct,
    open_interest,
    volume,
    -- Core PowerOptions metrics
    ROUND((stock_price - premium)::numeric, 2)                                  AS net_debit,
    ROUND(((strike_price - (stock_price - premium)) / (stock_price - premium) * 100)::numeric, 2) AS assigned_return_pct,
    ROUND(((strike_price - (stock_price - premium)) / (stock_price - premium) * 100 / dte * 365)::numeric, 1) AS annualized_return_pct,
    ROUND(((stock_price - (stock_price - premium)) / stock_price * 100)::numeric, 2) AS downside_protection_pct,
    earnings_date,
    days_to_earnings,
    ROUND(iv_rank::numeric, 1)                                                  AS iv_rank,
    ROUND(iv_percentile::numeric, 1)                                            AS iv_percentile,
    ROUND((hv_30d * 100)::numeric, 1)                                             AS hv_30d_pct,
    ROUND(market_cap::numeric / 1e9, 1)                                         AS market_cap_b,
    ROUND(trailing_pe::numeric, 1)                                              AS trailing_pe,
    avg_volume
FROM candidates
WHERE delta_rank = 1
ORDER BY annualized_return_pct DESC
