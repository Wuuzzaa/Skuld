DROP TABLE IF EXISTS "TableLog";
CREATE TABLE "TableLog" (
	table_name TEXT,
    timestamp DATETIME DEFAULT(datetime('subsec')),
    action TEXT,
    details TEXT,
    duration_seconds FLOAT,
    success BOOLEAN,
    rows_affected BIGINT,
    error_message TEXT,
    additional_info TEXT   
);