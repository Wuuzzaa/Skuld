-- sector_quadrants.sql
-- Aktuellen RRG-Quadrant je Sektor-ETF für den Screener.
-- Berechnet RS-Ratio + RS-Momentum analog src/sector_rotation.py,
-- aber nur den LETZTEN verfügbaren Tag (keine Zeitreihe).
--
-- Gibt zurück: etf_symbol, sector_name_de, rs_ratio, rs_momentum, quadrant
-- Quadrant: 'Leading' | 'Weakening' | 'Lagging' | 'Improving' | 'Unbekannt'
--
-- Params: keine (nimmt immer den neuesten Handelstag)

WITH benchmark AS (
    SELECT date, close AS bench_close
    FROM "StockPricesYahooHistory"
    WHERE symbol = 'SPY'
      AND date >= CURRENT_DATE - INTERVAL '30 days'
    UNION ALL
    SELECT CURRENT_DATE AS date, close AS bench_close
    FROM "StockPricesYahoo"
    WHERE symbol = 'SPY'
),
etf_prices AS (
    SELECT symbol, date, close
    FROM "StockPricesYahooHistory"
    WHERE symbol IN ('XLC','XLY','XLP','XLE','XLF','XLV','XLI','XLB','XLRE','XLK','XLU')
      AND date >= CURRENT_DATE - INTERVAL '30 days'
    UNION ALL
    SELECT symbol, CURRENT_DATE AS date, close
    FROM "StockPricesYahoo"
    WHERE symbol IN ('XLC','XLY','XLP','XLE','XLF','XLV','XLI','XLB','XLRE','XLK','XLU')
),
joined AS (
    SELECT
        e.symbol,
        e.date,
        e.close,
        b.bench_close,
        ROUND((e.close / NULLIF(b.bench_close, 0) * 100)::numeric, 4) AS raw_rs
    FROM etf_prices e
    JOIN benchmark b USING (date)
    WHERE e.close IS NOT NULL AND b.bench_close IS NOT NULL
),
-- 14-Tage SMA des raw_rs als RS-Ratio-Näherung, 1-Tage ROC als RS-Momentum-Näherung
windowed AS (
    SELECT
        symbol,
        date,
        raw_rs,
        AVG(raw_rs) OVER (
            PARTITION BY symbol ORDER BY date
            ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
        ) AS rs_ratio,
        raw_rs - LAG(raw_rs, 1) OVER (PARTITION BY symbol ORDER BY date) AS rs_mom_raw
    FROM joined
),
latest AS (
    SELECT DISTINCT ON (symbol)
        symbol,
        date,
        rs_ratio,
        -- Momentum: positiv = Improving/Leading, negativ = Weakening/Lagging
        -- Normiert auf 100-Basis wie RRG-Standard
        100 + COALESCE(rs_mom_raw, 0) * 10 AS rs_momentum
    FROM windowed
    WHERE rs_ratio IS NOT NULL
    ORDER BY symbol, date DESC
)
SELECT
    l.symbol                                           AS etf_symbol,
    CASE l.symbol
        WHEN 'XLC'  THEN 'Communication Services'
        WHEN 'XLY'  THEN 'Consumer Cyclical'
        WHEN 'XLP'  THEN 'Consumer Defensive'
        WHEN 'XLE'  THEN 'Energy'
        WHEN 'XLF'  THEN 'Financial Services'
        WHEN 'XLV'  THEN 'Healthcare'
        WHEN 'XLI'  THEN 'Industrials'
        WHEN 'XLB'  THEN 'Basic Materials'
        WHEN 'XLRE' THEN 'Real Estate'
        WHEN 'XLK'  THEN 'Technology'
        WHEN 'XLU'  THEN 'Utilities'
        ELSE l.symbol
    END                                                AS sector_en,
    ROUND(l.rs_ratio::numeric, 2)                      AS rs_ratio,
    ROUND(l.rs_momentum::numeric, 2)                   AS rs_momentum,
    CASE
        WHEN l.rs_ratio >= 100 AND l.rs_momentum >= 100 THEN 'Leading'
        WHEN l.rs_ratio >= 100 AND l.rs_momentum  < 100 THEN 'Weakening'
        WHEN l.rs_ratio  < 100 AND l.rs_momentum  < 100 THEN 'Lagging'
        WHEN l.rs_ratio  < 100 AND l.rs_momentum >= 100 THEN 'Improving'
        ELSE 'Unbekannt'
    END                                                AS quadrant
FROM latest l
ORDER BY l.symbol;
