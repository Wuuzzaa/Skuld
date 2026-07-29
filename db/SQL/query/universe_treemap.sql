-- Universe Treemap Query
-- Liefert alle Symbole mit Sektor, Branche, Kurs, Tagesperformance, Market Cap, IV Rank
-- Tagesperformance = (close - Summary_previousClose) / Summary_previousClose * 100

SELECT
    s.symbol,
    s.company_name,
    s.company_sector,
    s.company_industry,
    s.live_stock_price                                                  AS stock_price,
    s."Summary_previousClose"                                           AS prev_close,
    CASE
        WHEN s."Summary_previousClose" IS NOT NULL
             AND s."Summary_previousClose" > 0
        THEN ROUND(
            ((s.live_stock_price - s."Summary_previousClose")
             / s."Summary_previousClose" * 100.0)::numeric, 2)
        ELSE NULL
    END                                                                 AS price_change_pct,
    s."Summary_marketCap"                                               AS market_cap,
    ROUND((s."Summary_marketCap" / 1e9)::numeric, 2)                   AS market_cap_b,
    s.iv_rank,
    s."Summary_volume"                                                  AS volume,
    s."Summary_averageVolume"                                           AS avg_volume,
    s."Summary_beta"                                                    AS beta,
    s."Summary_fiftyTwoWeekLow"                                        AS week52_low,
    s."Summary_fiftyTwoWeekHigh"                                       AS week52_high,
    s."Summary_trailingPE"                                             AS trailing_pe,
    s."KeyStats_52WeekChange"                                          AS change_52w,
    -- Hat Optionen: Symbol ist in OptionDataMassive vorhanden
    CASE WHEN o.symbol IS NOT NULL THEN TRUE ELSE FALSE END            AS has_options
FROM
    "StockData" AS s
    LEFT JOIN (
        SELECT DISTINCT symbol FROM "OptionDataMassive"
    ) AS o ON s.symbol = o.symbol
WHERE
    s.company_sector IS NOT NULL
    AND s.live_stock_price IS NOT NULL
    AND s.live_stock_price > 0
ORDER BY
    s.company_sector,
    s.company_industry,
    s."Summary_marketCap" DESC NULLS LAST;
