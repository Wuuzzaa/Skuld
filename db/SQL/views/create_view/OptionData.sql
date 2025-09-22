DROP VIEW IF EXISTS OptionData;

CREATE VIEW
	OptionData AS
SELECT
	-- OptionDataYahoo
	a.symbol, 
	a."option-type", 
	a.expiration_date, 
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
	-- OptionDataTradingView
	CASE WHEN b.option_osi IS NOT NULL THEN TRUE ELSE FALSE END as has_option_data_tradingview,
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
	-- OptionPricingMetrics
	CASE WHEN c.contractSymbol IS NOT NULL THEN TRUE ELSE FALSE END as has_option_pricing_metrics,
	c.days_to_expiration,
	c.premium_option_price,
	c.intrinsic_value,
	c.extrinsic_value,
	c.moneyness
FROM
	OptionDataYahoo as a
	LEFT OUTER JOIN OptionDataTradingView AS b ON a.contractSymbol = b.option_osi
	-- b.symbol = b.symbol
	-- and b.strike = b.strike
	-- and b.expiration_date = b.expiration_date -- expiration_date in different formats 20250905 vs 2025-09-05 00:00:00.000000	
	-- and b."option-type" = b."option-type" -- option-type in different formats call vs calls
	LEFT OUTER JOIN OptionPricingMetrics as c ON a.contractSymbol = c.contractSymbol;