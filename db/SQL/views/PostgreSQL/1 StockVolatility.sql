CREATE OR REPLACE VIEW "StockVolatility" AS
SELECT
    a.symbol,
    a.historical_volatility_30d
FROM "StockHistoricalVolatilityYahoo" AS a;