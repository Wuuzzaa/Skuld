DROP VIEW IF EXISTS OptionDataHistory;
CREATE VIEW
	OptionDataHistory AS
SELECT
	a.date, 
	-- OptionDataYahooHistory
	a.symbol,
	a."option-type",
	DATE (a.expiration_date) as expiration_date,
	a.strike,
	a.bid,
	a.ask,
	a."contractSymbol",
	a.currency,
	a."lastPrice",
	a.change,
	a."percentChange",
	a.option_open_interest,
	a."contractSize",
	a."lastTradeDate",
	a."impliedVolatility",
	a."inTheMoney",
	a.option_volume,
	-- OptionDataTradingViewHistory
	CASE
		WHEN b.option_osi IS NOT NULL THEN TRUE
		ELSE FALSE
	END as has_option_data_tradingview,
	b.delta,
	b.gamma,
	b.iv,
	b.rho,
	b."theoPrice",
	b.theta,
	b.vega,
	b.option,
	b.time,
	b.exchange,
	b.option_osi,
	-- OptionPricingMetricsHistory
	CASE
		WHEN c.contractSymbol IS NOT NULL THEN TRUE
		ELSE FALSE
	END as has_option_pricing_metrics,
	c.days_to_expiration,
	c.premium_option_price,
	c.spread,
	c.spread_ptc,
	c.intrinsic_value,
	c.extrinsic_value,
	c.strike_stock_price_difference,
	c.strike_stock_price_difference_ptc
FROM
	OptionDataYahooHistory as a
	LEFT OUTER JOIN OptionDataTradingViewHistory AS b ON a.contractSymbol = b.option_osi
	-- b.symbol = b.symbol
	-- and b.strike = b.strike
	-- and b.expiration_date = b.expiration_date -- expiration_date in different formats 20250905 vs 2025-09-05 00:00:00.000000	
	-- and b."option-type" = b."option-type" -- option-type in different formats call vs calls
	AND a.date = b.date
	LEFT OUTER JOIN OptionPricingMetricsHistory as c ON a.contractSymbol = c.contractSymbol
	AND a.date = c.date;