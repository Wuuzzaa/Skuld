INSERT INTO "DataAgingFieldClassification"
(table_name, field_name, tier, tier_entry_date) 
VALUES
-- Kategorie: Master (Statische Kontraktinformationen)
('OptionDataMassive', 'option_osi', 'Master', DATE('now')),
('OptionDataMassive', 'symbol', 'Master', DATE('now')),
('OptionDataMassive', 'contract_type', 'Master', DATE('now')),
('OptionDataMassive', 'expiration_date', 'Master', DATE('now')),
('OptionDataMassive', 'strike_price', 'Master', DATE('now')),
('OptionDataMassive', 'exercize_style', 'Master', DATE('now')),
('OptionDataMassive', 'shares_per_contract', 'Master', DATE('now')),
('OptionDataMassive', 'implied_volatility', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_delta', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_gamma', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_theta', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_vega', 'Daily', DATE('now'))
ON CONFLICT(table_name, field_name) DO UPDATE SET
    tier = excluded.tier,
    tier_entry_date = excluded.tier_entry_date;

DROP TABLE IF EXISTS "StockDataBarchart";
DROP TABLE IF EXISTS "StockDataBarchartHistoryDaily";
DROP TABLE IF EXISTS "StockDataBarchartHistoryWeekly";
DROP TABLE IF EXISTS "StockDataBarchartHistoryMonthly";
DROP TABLE IF EXISTS "StockDataBarchartMasterData";

DROP TABLE IF EXISTS "OptionDataYahoo";
DROP TABLE IF EXISTS "OptionDataYahooHistoryDaily";
DROP TABLE IF EXISTS "OptionDataYahooHistoryWeekly";
DROP TABLE IF EXISTS "OptionDataYahooHistoryMonthly";
DROP TABLE IF EXISTS "OptionDataYahooMasterData";

DROP TABLE IF EXISTS "OptionDataTradingView";
DROP TABLE IF EXISTS "OptionDataTradingViewHistoryDaily";
DROP TABLE IF EXISTS "OptionDataTradingViewHistoryWeekly";
DROP TABLE IF EXISTS "OptionDataTradingViewHistoryMonthly";
DROP TABLE IF EXISTS "OptionDataTradingViewMasterData";