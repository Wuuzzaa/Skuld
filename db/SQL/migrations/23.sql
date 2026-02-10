INSERT INTO "DataAgingFieldClassification"
(table_name, field_name, tier, tier_entry_date) 
VALUES
-- Kategorie: Master (Statische Kontraktinformationen)
('OptionDataMassive', 'open_interest', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_delta', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_gamma', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_theta', 'Daily', DATE('now')),
('OptionDataMassive', 'greeks_vega', 'Daily', DATE('now')),

('OptionDataMassive', 'day_change', 'Daily', DATE('now')),
('OptionDataMassive', 'day_change_percent', 'Daily', DATE('now')),
('OptionDataMassive', 'day_close', 'Daily', DATE('now')),
('OptionDataMassive', 'day_high', 'Daily', DATE('now')),
('OptionDataMassive', 'day_low', 'Daily', DATE('now')),
('OptionDataMassive', 'day_open', 'Daily', DATE('now')),
('OptionDataMassive', 'day_previous_close', 'Daily', DATE('now')),
('OptionDataMassive', 'day_volume', 'Daily', DATE('now')),
('OptionDataMassive', 'day_vwap', 'Daily', DATE('now')),
('OptionDataMassive', 'exercise_style', 'Master', DATE('now')),
('OptionDataMassive', 'day_last_updated', 'Daily', DATE('now')),

('StockImpliedVolatilityMassive', 'iv', 'Daily', DATE('now')),
('StockImpliedVolatilityMassive', 'iv_low', 'Daily', DATE('now')),
('StockImpliedVolatilityMassive', 'iv_high', 'Daily', DATE('now')),
('StockImpliedVolatilityMassive', 'iv_rank', 'Daily', DATE('now')),
('StockImpliedVolatilityMassive', 'iv_percentile', 'Daily', DATE('now')),

('StockPricesYahoo', 'open', 'Daily', DATE('now')),
('StockPricesYahoo', 'high', 'Daily', DATE('now')),
('StockPricesYahoo', 'low', 'Daily', DATE('now')),
('StockPricesYahoo', 'close', 'Daily', DATE('now')),
('StockPricesYahoo', 'volume', 'Daily', DATE('now')),
('StockPricesYahoo', 'adjclose', 'Daily', DATE('now'))
ON CONFLICT(table_name, field_name) DO UPDATE SET
    tier = excluded.tier,
    tier_entry_date = excluded.tier_entry_date;
CREATE TABLE IF NOT EXISTS "StockImpliedVolatilityMassive"
(
    symbol text,
    iv double precision,
    iv_low double precision,
    iv_high double precision,
    iv_rank double precision,
    iv_percentile double precision,
    PRIMARY KEY (SYMBOL)
);
CREATE TABLE IF NOT EXISTS "StockImpliedVolatilityMassiveHistoryDaily"
(
    snapshot_date date,
    symbol text,
    iv double precision,
    iv_low double precision,
    iv_high double precision,
    iv_rank double precision,
    iv_percentile double precision,
    PRIMARY KEY (snapshot_date, symbol)
);