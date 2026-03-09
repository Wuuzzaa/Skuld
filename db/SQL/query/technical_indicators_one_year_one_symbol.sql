SELECT
    snapshot_date AS date,
    symbol,
    -- EMA
    ROUND("EMA_5"::numeric, 2) AS "EMA_5",
    ROUND("EMA_10"::numeric, 2) AS "EMA_10",
    ROUND("EMA_20"::numeric, 2) AS "EMA_20",
    ROUND("EMA_30"::numeric, 2) AS "EMA_30",
    ROUND("EMA_50"::numeric, 2) AS "EMA_50",
    ROUND("EMA_100"::numeric, 2) AS "EMA_100",
    ROUND("EMA_200"::numeric, 2) AS "EMA_200",
    -- SMA
    ROUND("SMA_5"::numeric, 2) AS "SMA_5",
    ROUND("SMA_10"::numeric, 2) AS "SMA_10",
    ROUND("SMA_20"::numeric, 2) AS "SMA_20",
    ROUND("SMA_30"::numeric, 2) AS "SMA_30",
    ROUND("SMA_50"::numeric, 2) AS "SMA_50",
    ROUND("SMA_100"::numeric, 2) AS "SMA_100",
    ROUND("SMA_200"::numeric, 2) AS "SMA_200",
    -- MACD
    ROUND("MACD_12_26_9"::numeric, 2) AS "MACD_12_26_9",
    ROUND("MACDh_12_26_9"::numeric, 2) AS "MACDh_12_26_9",
    ROUND("MACDs_12_26_9"::numeric, 2) AS "MACDs_12_26_9",
    -- Bollingerband
    ROUND("BBL_20_2.0_2.0"::numeric, 2) AS "BBL_20_2_0",
    ROUND("BBM_20_2.0_2.0"::numeric, 2) AS "BBM_20_2_0",
    ROUND("BBU_20_2.0_2.0"::numeric, 2) AS "BBU_20_2_0",
    ROUND("BBB_20_2.0_2.0"::numeric, 2) AS "BBB_20_2_0",
    ROUND("BBP_20_2.0_2.0"::numeric, 2) AS "BBP_20_2_0",
    -- ATR
    ROUND("ATRr_14"::numeric, 2) AS "ATRr_14",
    -- ADX
    ROUND("ADX_10"::numeric, 2) AS "ADX_10",
    ROUND("ADXR_10_2"::numeric, 2) AS "ADXR_10_2",
    -- Stochastic
    ROUND("STOCHk_14_3_1"::numeric, 2) AS "STOCHK_14_3_1",
    ROUND("STOCHd_14_3_1"::numeric, 2) AS "STOCHd_14_3_1",
    -- RSI
    ROUND("RSI_14"::numeric, 2) AS "RSL_14",
    -- RSL
    ROUND("RSL"::numeric, 2) AS "RSL",

    ROUND("DMP_10"::numeric, 2) AS "DMP_10",
    ROUND("DMN_10"::numeric, 2) AS "DMN_10"
FROM
    "TechnicalIndicatorsCalculatedHistoryDaily"
WHERE
    symbol = :symbol
    AND snapshot_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY
    snapshot_date DESC;
