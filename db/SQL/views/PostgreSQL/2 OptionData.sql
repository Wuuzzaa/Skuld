DROP VIEW IF EXISTS "OptionData" CASCADE;
CREATE VIEW
	"OptionData" AS
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

	-- OptionPricingMetrics
	d.days_to_expiration,
	d.premium_option_price,
	d.spread,
    d.spread_ptc,
	d.intrinsic_value,
	d.extrinsic_value,
	d.strike_stock_price_difference,
    d.strike_stock_price_difference_ptc
FROM
	"OptionDataMassive" AS a
	LEFT OUTER JOIN "OptionPricingMetrics" as d ON a.option_osi = d.option_osi;