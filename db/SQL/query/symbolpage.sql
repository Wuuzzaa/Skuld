SELECT DISTINCT
    symbol,
    company_name,
    company_industry,
	company_sector,
	company_country,
    ROUND(live_stock_price::numeric, 2) AS live_stock_price,
    ROUND(LAST_DIVIDEND::numeric, 2) AS LAST_DIVIDEND,
    LAST_DIVIDEND_DATE,
    NO_DIVIDEND_PAYOUTS_LAST_YEAR,
    dividend_classification,
    dividend_growth_years,
    ROUND(iv::numeric * 100, 2) AS iv,
    ROUND(iv_low::numeric * 100, 2) AS iv_low,
    ROUND(iv_high::numeric * 100, 2) AS iv_high,
    ROUND(iv_rank::numeric, 2) AS iv_rank,
    ROUND(iv_percentile::numeric, 2) AS iv_percentile,
    days_of_options_data_history,
    ROUND(historical_volatility_30d::numeric * 100, 2) AS historical_volatility_30d,
    ROUND("KeyStats_beta"::numeric, 2) AS Beta,
    earnings_date,
    analyst_mean_target
FROM "OptionDataMerged"
WHERE symbol = :symbol;