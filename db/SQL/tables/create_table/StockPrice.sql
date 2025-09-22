DROP TABLE IF EXISTS "StockPrice";
CREATE TABLE "StockPrice" (
	symbol TEXT, 
	live_stock_price FLOAT, 
	price_source TEXT, 
	live_price_timestamp DATETIME
);