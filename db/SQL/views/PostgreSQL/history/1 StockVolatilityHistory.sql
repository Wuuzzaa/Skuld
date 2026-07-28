CREATE OR REPLACE VIEW "StockVolatilityHistory" AS
SELECT
    date,
    symbol,
    historical_volatility_30d
FROM "StockHistoricalVolatilityYahooHistory";