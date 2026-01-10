CREATE TABLE IF NOT EXISTS "DataChangeLogs" (
    timestamp DATETIME NOT NULL,
    operation_type TEXT NOT NULL,
    table_name TEXT NOT NULL,
    affected_rows INTEGER,
    additional_data TEXT
);