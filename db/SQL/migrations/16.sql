DROP TABLE IF EXISTS "DatesHistory";
Create Table "DatesHistory"(
    date DATE PRIMARY KEY,
    year INT,
    month INT,
    week INT
);

INSERT INTO "DatesHistory"
(date, year, month, week)
SELECT DISTINCT
snapshot_date as date,
strftime ('%Y', snapshot_date) as year,
strftime ('%m', snapshot_date) as month,
strftime ('%W', snapshot_date) as week
FROM "OptionDataYahooHistoryDaily"
where 1=1
ON CONFLICT (date) DO NOTHING;

INSERT INTO "AnalystPriceTargetsMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "AnalystPriceTargetsHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "EarningDatesMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "EarningDatesHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "FundamentalDataDividendRadarMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "FundamentalDataDividendRadarHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "FundamentalDataYahooMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "FundamentalDataYahooHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "StockDataBarchartMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "StockDataBarchartHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "StockPriceMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "StockPriceHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "TechnicalIndicatorsMasterData" (
    "symbol"
)
SELECT DISTINCT
    "symbol"
FROM "TechnicalIndicatorsHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("symbol") DO NOTHING;

INSERT INTO "OptionDataTradingViewMasterData" (
    "option_osi"
)
SELECT DISTINCT
    "option_osi"
FROM "OptionDataTradingViewHistoryDaily"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("option_osi") DO NOTHING;

INSERT INTO "OptionDataYahooMasterData" (
     "contractSymbol"
)
SELECT DISTINCT
    "contractSymbol"
FROM "OptionDataYahoo"
WHERE 1=1 -- needed because of Parsing Ambiguity. Check SQLite documentation
ON CONFLICT("contractSymbol") DO NOTHING;