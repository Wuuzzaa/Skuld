DROP VIEW IF EXISTS OptionData;
CREATE VIEW
	OptionData AS
SELECT
	-- OptionDataMassive
	a."option_osi",
	a."symbol", 
	a."contract_type", 
	DATE(a."expiration_date") as expiration_date, 
	a."strike_price",  
	a.open_interest, 
    a.implied_volatility, 
	a."exercise_style", 
	a."shares_per_contract", 
	a."greeks_delta", 
	a."greeks_gamma", 
	a."greeks_theta", 
	a."greeks_vega", 
	a."day_change", 
	a."day_change_percent", 
	a."day_close", 
	a."day_high", 
	a."day_low", 
	a."day_open", 
	a."day_previous_close", 
	a."day_volume", 
	a."day_vwap",
	a."day_last_updated", 

	-- OptionDataYahoo
	b."option-type", 
	b.strike, 
	b.bid, 
	b.ask, 
	b."contractSymbol",
	b.currency,
	b."lastPrice",
	b.change,
	b."percentChange",
	b.option_open_interest,
	b."contractSize",
	b."lastTradeDate",
	b."impliedVolatility",
	b."inTheMoney",
	b.option_volume,

	-- OptionDataTradingView
	CASE WHEN c.option_osi IS NOT NULL THEN TRUE ELSE FALSE END as has_option_data_tradingview,
	c.delta,
	c.gamma,
	c.iv,
	c.rho,
	c."theoPrice",
	c.theta,
	c.vega,
	c.option,
	c.time,
	c.exchange,
	-- OptionPricingMetrics
	CASE WHEN d.option_osi IS NOT NULL THEN TRUE ELSE FALSE END as has_option_pricing_metrics,
	d.days_to_expiration,
	d.premium_option_price,
	d.spread,
    d.spread_ptc,
	d.intrinsic_value,
	d.extrinsic_value,
	d.strike_stock_price_difference,
    d.strike_stock_price_difference_ptc
FROM
	OptionDataMassive AS a
	LEFT OUTER JOIN OptionDataYahoo as b ON a.option_osi = b.contractSymbol
	LEFT OUTER JOIN OptionDataTradingView AS c ON a.option_osi = c.option_osi
	LEFT OUTER JOIN OptionPricingMetrics as d ON a.option_osi = d.option_osi;