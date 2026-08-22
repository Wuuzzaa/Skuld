-- strategy_finder_chain.sql
-- Zieht die vollständige Optionskette (Puts + Calls) für EIN Symbol über alle
-- Verfallstermine im gewünschten DTE-Fenster.
-- Keine bid/ask vorhanden → premium = day_close (Last Price).
-- Params: :symbol, :dte_min, :dte_max, :min_open_interest, :min_day_volume
SELECT
    o.symbol,
    o.contract_type                       AS option_type,
    o.strike_price,
    o.day_close                           AS premium,
    o.greeks_delta,
    o.implied_volatility,
    o.greeks_theta,
    o.open_interest,
    o.day_volume,
    o.expiration_date,
    o.days_to_expiration                  AS dte,
    o.live_stock_price                    AS stock_price,
    o.iv_rank,
    o.iv_percentile,
    o.historical_volatility_30d           AS hv_30d,
    o.earnings_date,
    o.days_to_earnings,
    o.company_name,
    o.company_sector,
    o.company_industry,
    o."Summary_marketCap"                 AS market_cap,
    -- Technische Indikatoren (Underlying-Ebene, LEFT JOIN -> NULL wenn nicht vorhanden)
    ti."RSI_14",
    ti."STOCHk_14_3_1",
    ti."STOCHh_14_3_1",
    ti."EMA_50",
    ti."EMA_200",
    ti."MACDh_12_26_9",
    ti."ADX_10",
    ti."DMP_10",
    ti."DMN_10",
    -- Beta für "Langweilige Aktien"-Filter (Market Cap ist bereits market_cap oben)
    f."KeyStats_beta"                     AS beta
FROM "OptionDataMerged" o
LEFT JOIN "TechnicalIndicatorsCalculated" ti ON ti.symbol = o.symbol
LEFT JOIN "FundamentalData" f ON f.symbol = o.symbol
WHERE o.symbol            = :symbol
  AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
  AND o.open_interest     >= :min_open_interest
  AND o.day_volume        >= :min_day_volume
  AND o.day_close         > 0
ORDER BY o.expiration_date ASC, o.contract_type DESC, o.strike_price ASC
