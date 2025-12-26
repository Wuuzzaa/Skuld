CREATE TABLE "DataAgingFieldClassification" (
    table_name TEXT NOT NULL,
    field_name TEXT NOT NULL,
    tier TEXT DEFAULT 'Daily', -- 'Daily', 'Weekly', 'Monthly', 'Master'
    last_value TEXT,
    last_change_date DATE,
    tier_entry_date DATE,
    PRIMARY KEY (table_name, field_name)
);