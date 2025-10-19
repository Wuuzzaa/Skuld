CREATE TABLE "OptionDataYahoo" (
	symbol TEXT, 
	expiration_date DATETIME, 
	"option-type" TEXT, 
	"contractSymbol" TEXT, 
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
	option_volume FLOAT
);