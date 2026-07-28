INSERT INTO "StockPricesYahooHistoryDaily" (snapshot_date, symbol, dividends,splits)
SELECT 
                daily.snapshot_date AS snapshot_date,
                master_data."symbol",
			coalesce(
                daily."dividends",
                master_data."dividends"
            ) as "dividends",
			coalesce(
                daily."splits",
                master_data."splits"
            ) as "splits"
            FROM
                "StockPricesYahooHistoryDaily" as daily
                LEFT OUTER JOIN "StockPricesYahooMasterData" as master_data
                ON master_data."symbol" = daily."symbol"
ON CONFLICT (snapshot_date, symbol)DO UPDATE SET
    dividends = excluded.dividends,
    splits = excluded.splits;

UPDATE "StockPricesYahooMasterData" SET "dividends" = NULL;
UPDATE "StockPricesYahooMasterData" SET "splits" = NULL;
UPDATE "StockPricesYahooHistoryDaily" SET "dividends" = NULL WHERE dividends = 0;
UPDATE "StockPricesYahooHistoryDaily" SET "splits" = NULL WHERE splits = 0;


INSERT INTO "DataAgingFieldClassification"
(table_name, field_name, tier, tier_entry_date) 
VALUES
-- Kategorie: Master (Statische Kontraktinformationen)
('TechnicalIndicatorsCalculated', 'BBM_20_2.0_2.0', 'Daily', DATE('now')),
('StockPricesYahoo', 'dividends', 'Daily', DATE('now')),
('StockPricesYahoo', 'splits', 'Daily', DATE('now'))
ON CONFLICT(table_name, field_name) DO UPDATE SET
    tier = excluded.tier,
    tier_entry_date = excluded.tier_entry_date;