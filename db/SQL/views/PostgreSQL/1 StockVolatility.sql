CREATE OR REPLACE VIEW "StockVolatility" AS
SELECT
    symbol,
    historical_volatility_30d
FROM "StockHistoricalVolatilityYahoo";