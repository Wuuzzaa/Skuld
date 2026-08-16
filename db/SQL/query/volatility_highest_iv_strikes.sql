-- Tab 3: Highest Implied Volatility — individual option strikes
-- Uses Last Price instead of Bid/Ask (no Bid/Ask available in this system)
SELECT
    m.symbol,
    m.expiration_date,
    m.contract_type                                             AS type,
    m.strike_price                                             AS strike,
    -- Moneyness: how far strike is from current price in %
    CASE
        WHEN s.adjclose > 0
        THEN (m.strike_price - s.adjclose) / s.adjclose * 100
        ELSE NULL
    END                                                        AS moneyness_pct,
    -- No Bid/Ask: use day_close (Last Price)
    m.day_close                                                AS last_price,
    m.day_volume                                               AS volume,
    m.implied_volatility                                       AS imp_vol,
    m.greeks_vega                                              AS vega,
    m.greeks_delta                                             AS delta,
    m.day_last_updated                                         AS last_trade,
    s.adjclose                                                 AS stock_price,
    (m.expiration_date::date - CURRENT_DATE)                   AS dte
FROM "OptionDataMassive" m
JOIN "StockPricesYahoo" s ON m.symbol = s.symbol
WHERE m.implied_volatility IS NOT NULL
  AND m.implied_volatility > 0
  AND m.day_close IS NOT NULL
  AND m.day_close > 0
  AND m.day_volume > 0
  AND m.expiration_date::date > CURRENT_DATE
  AND (m.expiration_date::date - CURRENT_DATE) BETWEEN 1 AND :max_dte
  AND m.contract_type = :option_type
ORDER BY m.implied_volatility DESC
LIMIT :limit_rows;
