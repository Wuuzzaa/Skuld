DROP TABLE IF EXISTS "StockPrice";
CREATE TABLE "StockPrice" (
	symbol TEXT PRIMARY KEY, 
	live_stock_price FLOAT, 
	price_source TEXT, 
	live_price_timestamp DATETIME
);