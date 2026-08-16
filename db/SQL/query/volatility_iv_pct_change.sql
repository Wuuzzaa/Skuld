-- Tab 4: Options % Change in Volatility — strikes with biggest IV move vs yesterday
WITH yesterday_strikes AS (
    SELECT
        h.option_osi,
        h.implied_volatility AS iv_yesterday
    FROM "OptionDataMassiveHistoryDaily" h
    WHERE h.snapshot_date = (
        SELECT MAX(snapshot_date)
        FROM "OptionDataMassiveHistoryDaily"
        WHERE snapshot_date < CURRENT_DATE
    )
)
SELECT
    m.symbol,
    s.adjclose                                                  AS stock_price,
    m.expiration_date,
    m.contract_type                                             AS type,
    m.strike_price                                             AS strike,
    CASE
        WHEN s.adjclose > 0
        THEN (m.strike_price - s.adjclose) / s.adjclose * 100
        ELSE NULL
    END                                                        AS moneyness_pct,
    m.day_close                                                AS last_price,
    m.day_volume                                               AS volume,
    -- IV % change vs yesterday
    CASE
        WHEN y.iv_yesterday IS NOT NULL AND y.iv_yesterday > 0
        THEN (m.implied_volatility - y.iv_yesterday) / y.iv_yesterday * 100
        ELSE NULL
    END                                                        AS iv_pct_chg,
    m.implied_volatility                                       AS imp_vol,
    m.greeks_vega                                              AS vega,
    m.greeks_delta                                             AS delta,
    m.day_last_updated                                         AS last_trade,
    (m.expiration_date::date - CURRENT_DATE)                   AS dte
FROM "OptionDataMassive" m
JOIN "StockPricesYahoo" s    ON m.symbol = s.symbol
LEFT JOIN yesterday_strikes y ON m.option_osi = y.option_osi
WHERE m.implied_volatility IS NOT NULL
  AND m.implied_volatility > 0
  AND m.day_close IS NOT NULL
  AND m.day_close > 0
  AND m.day_volume > 0
  AND m.expiration_date::date > CURRENT_DATE
  AND (m.expiration_date::date - CURRENT_DATE) BETWEEN 1 AND :max_dte
  AND y.iv_yesterday IS NOT NULL
  AND :direction IN ('increase', 'decrease')
  AND (
      (:direction = 'increase' AND m.implied_volatility > y.iv_yesterday)
      OR
      (:direction = 'decrease' AND m.implied_volatility < y.iv_yesterday)
  )
ORDER BY
    CASE WHEN :direction = 'increase'
         THEN (m.implied_volatility - y.iv_yesterday) / y.iv_yesterday * 100
         ELSE NULL END DESC NULLS LAST,
    CASE WHEN :direction = 'decrease'
         THEN (m.implied_volatility - y.iv_yesterday) / y.iv_yesterday * 100
         ELSE NULL END ASC NULLS LAST
LIMIT :limit_rows;
