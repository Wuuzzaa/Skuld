WITH FilteredCalls AS (
    SELECT
        symbol,
        company_name,
        company_sector,
        company_industry,
        live_stock_price AS stock_price,
        strike_price,
        day_close AS premium,
        days_to_expiration AS "DTE",
        expiration_date,
        abs(greeks_delta) AS delta,
        implied_volatility AS iv,
        open_interest,
        day_volume AS volume,
        earnings_date AS earnings_date_next,
        days_to_earnings,
        "SMA_20",
        "SMA_50",
        "SMA_200",
        iv_rank,
        iv_percentile,
        -- PowerOptions filters
        "MACD_12_26_9" AS macd,
        "MACDs_12_26_9" AS macd_signal,
        "MACDh_12_26_9" AS macd_histogram,
        "RSI_14" AS rsi_14,
        "Forward_EPS_Growth_Percent" AS eps_growth,
        "Summary_trailingPE" AS pe_ratio,
        "FinData_recommendationMean" AS analyst_recommendation,
        "Summary_averageVolume" AS avg_volume,
        "MarketCap" AS market_cap,
        historical_volatility_30d AS hv_30d,
        ROW_NUMBER() OVER (
            PARTITION BY symbol
            ORDER BY ABS(abs(greeks_delta) - :delta_target) ASC
        ) AS delta_rank
    FROM
        "OptionDataMerged"
    WHERE
        contract_type = 'call'
        AND expiration_date = :expiration_date
        AND strike_price <= live_stock_price
        AND open_interest >= :min_open_interest
        AND day_close > 0
        AND live_stock_price > 0
)
SELECT * FROM FilteredCalls
WHERE delta_rank <= :max_per_symbol
ORDER BY symbol, delta_rank
