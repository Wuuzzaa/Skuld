DROP TABLE IF EXISTS "OptionDataYahoo";
CREATE TABLE "OptionDataYahoo" (
	"contractSymbol" TEXT,
	symbol TEXT,
	"option-type" TEXT, 
	expiration_date DATETIME, 
	strike FLOAT, 
	currency TEXT, 
	"lastPrice" FLOAT, 
	change FLOAT, 
	"percentChange" FLOAT, 
	option_open_interest BIGINT, 
	bid FLOAT, 
	ask FLOAT, 
	"contractSize" TEXT, 
	"lastTradeDate" DATETIME, 
	"impliedVolatility" FLOAT, 
	"inTheMoney" BOOLEAN, 
	option_volume FLOAT,
	PRIMARY KEY("contractSymbol")
);