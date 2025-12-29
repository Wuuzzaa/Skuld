DROP TABLE IF EXISTS "OptionDataTradingView";
CREATE TABLE "OptionDataTradingView" (
	option_osi TEXT,
	symbol TEXT, 
	"option-type" TEXT,
	expiration_date BIGINT,
	strike FLOAT, 
	ask FLOAT, 
	bid FLOAT, 
	delta FLOAT, 
	gamma FLOAT, 
	iv FLOAT, 
	rho FLOAT, 
	"theoPrice" FLOAT, 
	theta FLOAT, 
	vega FLOAT, 
	option TEXT, 
	time TEXT, 
	exchange TEXT,
	PRIMARY KEY(option_osi)
);