CREATE TABLE IF NOT EXISTS DataChangeLogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    operation_type TEXT NOT NULL,
    table_name TEXT NOT NULL,
    affected_rows INTEGER,
    additional_data TEXT
);