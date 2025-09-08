SELECT * FROM OptionData;

SELECT 
	a.symbol, 
	a."option-type", 
	a.strike, 
	a.expiration_date,
    b.expiration_date,
    a.option_osi,
    b.contractSymbol,
    a."option-type",
    b."option-type",
    COUNT(*) AS count
FROM 
    OptionDataTradingView AS a
JOIN 
    OptionDataYahoo as b
ON 
    a.symbol = b.symbol
    and a.strike = b.strike
    and a.expiration_date = b.expiration_date
    and a."option-type" = b."option-type";