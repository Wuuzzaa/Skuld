-- Enhanced Spreads Query (Multi-Date / performance-optimiert)
-- Unterschiede zu spreads_enhanced_input.sql:
--   1) expiration_date + option_type werden FRUEH in FilteredOptions gefiltert
--      (statt erst in TargetOptions) -> die CTE materialisiert nur die relevanten
--      Zeilen statt aller ~117k Optionen. ~20% schneller pro Lauf.
--   2) Mehrere Verfallstermine in EINER Query via IN-Liste. Der Platzhalter
--      __EXP_LIST__ wird von der Page durch die noetigen Datums-Binds ersetzt
--      (Einzel-Params, kein PG-Array-Binding). ROW_NUMBER partitioniert weiterhin
--      pro (symbol, expiration_date, option_type), also ein Delta-Ranking je Termin.
-- WICHTIG: keine doppelpunkt-Parameter-Beispiele in Kommentaren schreiben!
--      SQLAlchemy text() parst solche Vorkommen als echte Bind-Parameter und
--      verlangt dann Werte dafuer (fuehrte zu "value required for bind parameter d1").
WITH FilteredOptions AS (
    SELECT
        option_osi,
        symbol,
        expiration_date,
        contract_type AS option_type,
        strike_price AS strike,
        day_close AS last_option_price,
        abs(greeks_delta) AS delta,
        implied_volatility AS iv,
        greeks_theta AS theta,
        LIVE_STOCK_PRICE AS close,
        earnings_date,
        days_to_expiration,
        days_to_earnings,
        open_interest AS option_open_interest,
        expected_move,
        analyst_mean_target,
        day_volume,
        day_last_updated,
        company_name,
        company_industry,
        company_sector,
        historical_volatility_30d,
        iv_rank,
        iv_percentile,
        last_updated_option_data,
        last_updated_stock_data
    FROM
        "OptionDataMerged" AS a
    WHERE
        open_interest >= :min_open_interest
        AND day_volume >= :min_day_volume
        AND (:min_iv_rank <= 0 OR iv_rank IS NULL OR iv_rank >= :min_iv_rank)
        AND (:min_iv_percentile <= 0 OR iv_percentile IS NULL OR iv_percentile >= :min_iv_percentile)
        -- exp_date + option_type FRUEH -> CTE bleibt schlank
        AND expiration_date IN (__EXP_LIST__)
        AND contract_type = :option_type
        -- Asset-Typ-Filter. asset_type: 'all' | 'stock' | 'etf' | 'index'
        AND (
            :asset_type = 'all'
            OR (:asset_type = 'index' AND symbol LIKE 'I:%')
            OR (:asset_type = 'stock' AND symbol NOT LIKE 'I:%' AND company_sector IS NOT NULL AND company_sector <> '')
            OR (:asset_type = 'etf'   AND symbol NOT LIKE 'I:%' AND (company_sector IS NULL OR company_sector = ''))
        )
),

TargetOptions AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY symbol, expiration_date, option_type
            ORDER BY abs(delta - :delta_target) ASC
        ) as delta_rank
    FROM
        FilteredOptions
)

SELECT
    -- symbol data
    sell.symbol,
    -- technische Indikatoren (LEFT JOIN -> NULL wenn nicht vorhanden)
    ti."STOCHk_14_3_1",
    ti."STOCHd_14_3_1",
    ti."STOCHh_14_3_1",
    ti."RSI_14",
    ti."EMA_50",
    ti."EMA_200",
    ti."MACDh_12_26_9",
    ti."ADX_10",
    ti."DMP_10",
    ti."DMN_10",
    -- Technischer Timing-Score (0-6), RICHTUNGSABHAENGIG + STIL-abhaengig.
    -- :score_direction = 'bull' (Bull Put) | 'bear' (Bear Call, gespiegelt)
    -- :score_style     = 'trend' | 'dip'
    --   'trend' = Schule A: Aktie stabil im Trend, NICHT ueberverkauft (kein fallendes Messer).
    --   'dip'   = Schule B: in den Ruecksetzer verkaufen (ueberverkauft = hohe Praemie + Rebound).
    -- Fachliche Begruendung je Kriterium siehe Doku-Expander in der Page.
    (
        CASE
            -- ── BULL / TREND (Schule A, Default) ──────────────────────────────
            -- Aktie stabil im Aufwaertstrend, gesundes Momentum, NICHT im Extrem.
            -- RSI-Fenster 45-70: Cardwell "range shift" -> Aufwaertstrend traegt RSI ~40-80,
            -- 45-70 = gesunde Staerke ohne die Ueberkauft-Extremzone (>70).
            WHEN :score_direction = 'bull' AND :score_style = 'trend' THEN (
                CASE WHEN sell.close > ti."EMA_200" THEN 1 ELSE 0 END +          -- Aufwaertstrend (200er)
                CASE WHEN sell.close > ti."EMA_50"  THEN 1 ELSE 0 END +          -- Trend intakt (50er)
                CASE WHEN ti."RSI_14" BETWEEN 45 AND 70 THEN 1 ELSE 0 END +      -- gesunde Staerke, nicht ueberkauft
                CASE WHEN ti."STOCHk_14_3_1" BETWEEN 20 AND 80 THEN 1 ELSE 0 END +  -- Mittelfeld (weder ueber-/unterkauft)
                CASE WHEN ti."ADX_10" > 18 AND ti."DMP_10" > ti."DMN_10" THEN 1 ELSE 0 END +  -- Aufwaertstrend m. Substanz
                CASE WHEN ti."MACDh_12_26_9" > 0 THEN 1 ELSE 0 END               -- Momentum oben
            )
            -- ── BULL / DIP (Schule B) ─────────────────────────────────────────
            WHEN :score_direction = 'bull' AND :score_style = 'dip' THEN (
                CASE WHEN sell.close > ti."EMA_200" THEN 1 ELSE 0 END +          -- uebergeordneter Trend intakt
                CASE WHEN ti."RSI_14" BETWEEN 30 AND 45 THEN 1 ELSE 0 END +      -- Pullback-Zone
                CASE WHEN ti."STOCHk_14_3_1" < 20 THEN 1 ELSE 0 END +            -- kurzfristig ueberverkauft
                CASE WHEN ti."STOCHh_14_3_1" > 0 THEN 1 ELSE 0 END +             -- Stochastik dreht hoch
                CASE WHEN ti."ADX_10" > 18 AND ti."DMP_10" > ti."DMN_10" THEN 1 ELSE 0 END +  -- Trend weiterhin auf
                CASE WHEN ti."MACDh_12_26_9" > 0 THEN 1 ELSE 0 END               -- Momentum dreht hoch
            )
            -- ── BEAR / TREND (Schule A gespiegelt) ────────────────────────────
            -- Exakt gespiegelt: Aktie stabil im Abwaertstrend, NICHT im Extrem.
            -- RSI 30-55 = gespiegeltes Cardwell-Fenster (Abwaertstrend traegt RSI ~20-60).
            WHEN :score_direction = 'bear' AND :score_style = 'trend' THEN (
                CASE WHEN sell.close < ti."EMA_200" THEN 1 ELSE 0 END +          -- Abwaertstrend (200er)
                CASE WHEN sell.close < ti."EMA_50"  THEN 1 ELSE 0 END +          -- Trend intakt (50er)
                CASE WHEN ti."RSI_14" BETWEEN 30 AND 55 THEN 1 ELSE 0 END +      -- gesunde Schwaeche, nicht ueberverkauft
                CASE WHEN ti."STOCHk_14_3_1" BETWEEN 20 AND 80 THEN 1 ELSE 0 END +  -- Mittelfeld
                CASE WHEN ti."ADX_10" > 18 AND ti."DMN_10" > ti."DMP_10" THEN 1 ELSE 0 END +  -- Abwaertstrend m. Substanz
                CASE WHEN ti."MACDh_12_26_9" < 0 THEN 1 ELSE 0 END               -- Momentum unten
            )
            -- ── BEAR / DIP (Schule B gespiegelt = ueberkaufter Rip verkaufen) ──
            WHEN :score_direction = 'bear' AND :score_style = 'dip' THEN (
                CASE WHEN sell.close < ti."EMA_200" THEN 1 ELSE 0 END +
                CASE WHEN ti."RSI_14" BETWEEN 55 AND 70 THEN 1 ELSE 0 END +
                CASE WHEN ti."STOCHk_14_3_1" > 80 THEN 1 ELSE 0 END +
                CASE WHEN ti."STOCHh_14_3_1" < 0 THEN 1 ELSE 0 END +
                CASE WHEN ti."ADX_10" > 18 AND ti."DMN_10" > ti."DMP_10" THEN 1 ELSE 0 END +
                CASE WHEN ti."MACDh_12_26_9" < 0 THEN 1 ELSE 0 END
            )
            ELSE 0
        END
    ) AS tech_score,
    sell.expiration_date,
    sell.option_type,
    sell.close,
    sell.earnings_date,
    sell.company_name AS "Company",
    sell.days_to_expiration,
    sell.days_to_earnings,
    sell.analyst_mean_target,
    sell.company_industry,
    sell.company_sector,
    CASE
        WHEN sell.symbol LIKE 'I:%' THEN 'index'
        WHEN sell.company_sector IS NULL OR sell.company_sector = '' THEN 'etf'
        ELSE 'stock'
    END AS asset_type,
    sell.historical_volatility_30d,
    sell.iv_rank,
    sell.iv_percentile,
    sell.delta_rank,
    -- sell option
    sell.option_osi AS sell_option_osi,
    sell.strike AS sell_strike,
    sell.last_option_price AS sell_last_option_price,
    sell.delta AS sell_delta,
    sell.iv AS sell_iv,
    sell.theta AS sell_theta,
    sell.option_open_interest AS sell_open_interest,
    sell.expected_move AS sell_expected_move,
    sell.day_volume AS sell_day_volume,
    sell.day_last_updated AS sell_last_updated,
    -- buy option
    buy.option_osi AS buy_option_osi,
    buy.strike AS buy_strike,
    buy.last_option_price AS buy_last_option_price,
    buy.delta AS buy_delta,
    buy.iv AS buy_iv,
    buy.theta AS buy_theta,
    buy.option_open_interest AS buy_open_interest,
    buy.expected_move AS buy_expected_move,
    buy.day_volume AS buy_day_volume,
    buy.day_last_updated AS buy_last_updated,
    buy.last_updated_option_data,
    buy.last_updated_stock_data
FROM
    TargetOptions sell
INNER JOIN
    FilteredOptions buy
    ON sell.symbol = buy.symbol
    AND sell.expiration_date = buy.expiration_date
    AND sell.option_type = buy.option_type
    AND buy.strike != sell.strike
    AND (
        CASE
            WHEN :strategy_type = 'credit' THEN
                CASE
                    WHEN sell.option_type = 'put'  THEN buy.strike BETWEEN sell.strike - :spread_width AND sell.strike - :spread_width_min
                    WHEN sell.option_type = 'call' THEN buy.strike BETWEEN sell.strike + :spread_width_min AND sell.strike + :spread_width
                END
            WHEN :strategy_type = 'debit' THEN
                CASE
                    WHEN sell.option_type = 'put'  THEN buy.strike BETWEEN sell.strike + :spread_width_min AND sell.strike + :spread_width
                    WHEN sell.option_type = 'call' THEN buy.strike BETWEEN sell.strike - :spread_width AND sell.strike - :spread_width_min
                END
        END
    )
LEFT JOIN
    "TechnicalIndicatorsCalculated" ti ON ti.symbol = sell.symbol
WHERE
    sell.delta_rank <= :delta_candidates;
