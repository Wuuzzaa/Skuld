-- put_screener.sql
-- CSP-Einstiegs-Screener: qualifizierte Aktie (StockData) + bester passender Put
-- (OptionDataMerged) = eine Zeile je Aktie.
--
-- Harte Filter (Buch Kap. 4): Preis 15-80$, Options-Liquidität OI/Vol >= 100.
-- Scoring (Punkte) macht src/put_screener.py auf den hier gelieferten Spalten.
--
-- Bester Put je Aktie: Strike am nächsten zum aktuellen Kurs (am Geld),
-- DTE-Fenster 21-45 (~30, monatlich bevorzugt via UI/get_expiration_type),
-- bei Gleichstand höchstes Open Interest.
--
-- Params: :dte_min (z.B. 21), :dte_max (z.B. 45), :min_oi (>=100), :min_vol (>=100),
--         :price_min / :price_max (Aktienkurs-Fenster, Default Buch 15..80),
--         :min_premium_share (Mindestprämie je Aktie, z.B. 0.50 = 50$ pro Kontrakt),
--         :min_market_cap (Mindest Market Cap in $, z.B. 2e9 = 2 Mrd.)
-- Spaltennamen gegen dividend_screener.sql / covered_call_scanner.sql verifiziert.
WITH puts AS (
    SELECT DISTINCT ON (o.symbol)
        o.symbol,
        o.strike_price,
        o.expiration_date,
        o.days_to_expiration,
        o.premium_option_price,
        o.open_interest,
        o.day_volume,
        o.greeks_delta,
        o.implied_volatility,
        o.iv_rank,
        o.live_stock_price
    FROM "OptionDataMerged" o
    WHERE o.contract_type = 'put'
      AND o.days_to_expiration BETWEEN :dte_min AND :dte_max
    AND o.premium_option_price >= :min_premium_share
      AND o.open_interest >= :min_oi
      AND o.day_volume    >= :min_vol
      AND o.live_stock_price BETWEEN :price_min AND :price_max
    ORDER BY o.symbol,
             ABS(o.strike_price - o.live_stock_price) ASC,  -- am nächsten zum Geld
             o.open_interest DESC                            -- Gleichstand: liquidester
)
SELECT
    s.symbol,
    s.company_name,
    s.company_sector                                   AS sector,
    s.company_industry                                 AS industry,
    ROUND(p.live_stock_price::numeric, 2)              AS price,
    ROUND(s."MarketCap"::numeric, 0)                   AS market_cap,

    -- Proxy-Kriterien "aktuell" (kein Mehrjahres-Trend verfügbar)
    ROUND(s."FinData_revenueGrowth"::numeric * 100, 2) AS revenue_growth_pct,
    ROUND(s."Forward_EPS_Growth_Percent"::numeric, 2)  AS eps_growth_pct,
    ROUND(s."OperatingCashFlow"::numeric, 0)           AS operating_cashflow,
    ROUND(s."FreeCashFlow"::numeric, 0)                AS free_cashflow,

    -- Voll abbildbare Fundamentaldaten
    ROUND(s."Summary_payoutRatio"::numeric * 100, 2)   AS payout_ratio_pct,
    ROUND(s."Summary_trailingPE"::numeric, 2)          AS trailing_pe,
    ROUND(s."KeyStats_forwardPE"::numeric, 2)          AS forward_pe,

    -- Zusätzliche Felder für KI-Zuteilungsrisiko-Analyse
    ROUND(s."FinData_debtToEquity"::numeric, 2)        AS debt_to_equity,
    ROUND(s."FinData_grossMargins"::numeric * 100, 2)  AS gross_margin_pct,
    ROUND(s."FinData_returnOnEquity"::numeric * 100, 2) AS return_on_equity_pct,
    ROUND(s."KeyStats_shortPercentOfFloat"::numeric * 100, 2) AS short_percent_float,

    -- Timing (Kap. 5)
    ROUND(s."RSI_14"::numeric, 2)                      AS rsi_14,
    ROUND(s."MACDh_12_26_9"::numeric, 4)               AS macd_histogram,
    ROUND(s."SMA_200"::numeric, 2)                     AS sma_200,
    ROUND(s."Summary_fiftyTwoWeekLow"::numeric, 2)     AS week_52_low,

    -- Bester Put
    ROUND(p.strike_price::numeric, 2)                  AS put_strike,
    p.expiration_date                                  AS put_expiry,
    p.days_to_expiration                               AS put_dte,
    ROUND(p.premium_option_price::numeric, 2)          AS put_premium,
    p.open_interest                                    AS put_oi,
    p.day_volume                                       AS put_volume,
    ROUND(p.greeks_delta::numeric, 3)                  AS put_delta,
    ROUND(p.iv_rank::numeric, 2)                       AS iv_rank,
    ROUND(p.implied_volatility::numeric, 4)            AS put_iv,

    -- Convenience: Rendite / Gewinnschwelle / Kapital
    ROUND((p.premium_option_price / NULLIF(p.strike_price, 0) * 100)::numeric, 2)        AS premium_pct,
    ROUND(((p.premium_option_price / NULLIF(p.strike_price, 0))
           * (365.0 / NULLIF(p.days_to_expiration, 0)) * 100)::numeric, 2)               AS annualized_pct,
    ROUND((p.strike_price - p.premium_option_price)::numeric, 2)                          AS breakeven,
    ROUND((p.strike_price * 100)::numeric, 0)                                             AS capital_required
FROM "StockData" s
JOIN puts p ON p.symbol = s.symbol
WHERE s.live_stock_price IS NOT NULL
  AND (s."MarketCap" IS NULL OR s."MarketCap" >= :min_market_cap)
  AND p.strike_price < s.live_stock_price  -- Nur OTM Puts (nicht ITM!)
ORDER BY s.symbol
