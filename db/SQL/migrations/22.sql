DROP TABLE IF EXISTS "StockDayPricesYahooHistoryDaily" ;
DROP TABLE IF EXISTS "StockDayPricesYahoo";
DROP TABLE IF EXISTS "StockPricesYahooHistoryDaily" ;
DROP TABLE IF EXISTS "StockPricesYahoo";
CREATE TABLE IF NOT EXISTS "StockPricesYahooHistoryDaily" (
	snapshot_date DATE,
    symbol TEXT,
	open DOUBLE PRECISION,
	high DOUBLE PRECISION,
	low DOUBLE PRECISION,
	close DOUBLE PRECISION,
	volume BIGINT,
	adjclose DOUBLE PRECISION,
	dividends REAL,
	splits DOUBLE PRECISION,
	PRIMARY KEY (snapshot_date,symbol)
);
CREATE TABLE IF NOT EXISTS "StockPricesYahoo" (
    symbol TEXT,
	open DOUBLE PRECISION,
	high DOUBLE PRECISION,
	low DOUBLE PRECISION,
	close DOUBLE PRECISION,
	volume BIGINT,
	adjclose DOUBLE PRECISION,
	dividends REAL,
	splits DOUBLE PRECISION,
	PRIMARY KEY (symbol)
);