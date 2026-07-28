INSERT INTO "AnalystPriceTargetsHistoryDaily" (snapshot_date, symbol, analyst_mean_target)
SELECT 
    dates.date as snapshot_date,
    master_data."symbol",
    coalesce(
            daily."analyst_mean_target",
            master_data."analyst_mean_target"
        ) as "analyst_mean_target"
FROM
    "DatesHistory" as dates
    INNER JOIN "AnalystPriceTargetsMasterData" as master_data
    ON dates.date BETWEEN master_data.from_date AND master_data.to_date 
    LEFT OUTER JOIN "AnalystPriceTargetsHistoryDaily" as daily
ON dates.date = daily.snapshot_date
AND master_data."symbol" = daily."symbol"
ON CONFLICT (snapshot_date, symbol)DO UPDATE SET
    analyst_mean_target = excluded.analyst_mean_target;
UPDATE "AnalystPriceTargetsMasterData" SET "analyst_mean_target" = NULL;

INSERT INTO "DividendDataYahooHistoryDaily" (snapshot_date, symbol, years_of_growth,classification)
SELECT 
    dates.date as snapshot_date,
    master_data."symbol",
coalesce(
        daily."years_of_growth",
        master_data."years_of_growth"
    ) as "years_of_growth",
coalesce(
        daily."classification",
        master_data."classification"
    ) as "classification"
FROM
    "DatesHistory" as dates
    INNER JOIN "DividendDataYahooMasterData" as master_data
    ON dates.date BETWEEN master_data.from_date AND master_data.to_date 
    LEFT OUTER JOIN "DividendDataYahooHistoryDaily" as daily
ON dates.date = daily.snapshot_date
AND master_data."symbol" = daily."symbol"
ON CONFLICT (snapshot_date, symbol)DO UPDATE SET
    years_of_growth = excluded.years_of_growth,
    classification = excluded.classification;
UPDATE "DividendDataYahooMasterData" SET "years_of_growth" = NULL;
UPDATE "DividendDataYahooMasterData" SET "classification" = NULL;

INSERT INTO "EarningDatesHistoryDaily" (snapshot_date, symbol, earnings_date)
SELECT 
    dates.date as snapshot_date,
    master_data."symbol",
coalesce(
        daily."earnings_date",
        master_data."earnings_date"
    ) as "earnings_date"
FROM
    "DatesHistory" as dates
    INNER JOIN "EarningDatesMasterData" as master_data
    ON dates.date BETWEEN master_data.from_date AND master_data.to_date 
    LEFT OUTER JOIN "EarningDatesHistoryDaily" as daily
ON dates.date = daily.snapshot_date
AND master_data."symbol" = daily."symbol"
ON CONFLICT (snapshot_date, symbol)DO UPDATE SET
    earnings_date = excluded.earnings_date;
UPDATE "EarningDatesMasterData" SET "earnings_date" = NULL;

TRUNCATE TABLE "StockAssetProfilesYahooHistoryDaily";

INSERT INTO "StockHistoricalVolatilityYahooHistoryDaily" (snapshot_date, symbol, historical_volatility_30d)
SELECT 
    dates.date as snapshot_date,
    master_data."symbol",
coalesce(
        daily."historical_volatility_30d",
        master_data."historical_volatility_30d"
    ) as "historical_volatility_30d"
FROM
    "DatesHistory" as dates
    INNER JOIN "StockHistoricalVolatilityYahooMasterData" as master_data
    ON dates.date BETWEEN master_data.from_date AND master_data.to_date 
    LEFT OUTER JOIN "StockHistoricalVolatilityYahooHistoryDaily" as daily
ON dates.date = daily.snapshot_date
AND master_data."symbol" = daily."symbol"
ON CONFLICT (snapshot_date, symbol)DO UPDATE SET
    historical_volatility_30d = excluded.historical_volatility_30d;
UPDATE "StockHistoricalVolatilityYahooMasterData" SET "historical_volatility_30d" = NULL;    

INSERT INTO "DataAgingFieldClassification"
(table_name, field_name, tier, tier_entry_date) 
VALUES
-- Kategorie: Master (Statische Kontraktinformationen)
('AnalystPriceTargets', 'analyst_mean_target', 'Daily', DATE('now')),
('DividendDataYahoo', 'years_of_growth', 'Daily', DATE('now')),
('DividendDataYahoo', 'classification', 'Daily', DATE('now')),
('EarningDates', 'earnings_date', 'Daily', DATE('now')),
('StockAssetProfilesYahoo', 'name', 'Master', DATE('now')),
('StockAssetProfilesYahoo', 'industry', 'Master', DATE('now')),
('StockAssetProfilesYahoo', 'sector', 'Master', DATE('now')),
('StockAssetProfilesYahoo', 'country', 'Master', DATE('now')),
('StockAssetProfilesYahoo', 'long_business_summary', 'Master', DATE('now')),
('StockHistoricalVolatilityYahoo', 'historical_volatility_30d', 'Daily', DATE('now'))
ON CONFLICT(table_name, field_name) DO UPDATE SET
    tier = excluded.tier,
    tier_entry_date = excluded.tier_entry_date;