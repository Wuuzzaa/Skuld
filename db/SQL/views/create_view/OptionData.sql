DROP VIEW IF EXISTS OptionData;

CREATE VIEW OptionData AS
SELECT 
	a.symbol, 
	a."option-type", 
	a.strike, 
	a.expiration_date, 
    a.ask, 
	a.bid, 
	a.delta, 
	a.gamma, 
	a.iv, 
	a.rho, 
    a."theoPrice", 
	a.theta, 
	a.vega, 
	a.option, 
	a.time, 
	a.exchange, 
	a.option_osi,
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
	b.option_volume
FROM 
    OptionDataTradingView AS a
JOIN 
    OptionDataYahoo as b
ON a.option_osi = b.contractSymbol;
    -- a.symbol = b.symbol
    -- and a.strike = b.strike
    -- and a.expiration_date = b.expiration_date -- expiration_date in different formats 20250905 vs 2025-09-05 00:00:00.000000	
    -- and a."option-type" = b."option-type"; -- option-type in different formats call vs calls