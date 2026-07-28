-- SystemSettings table for storing application configuration
CREATE TABLE IF NOT EXISTS "SystemSettings"
(
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default log level setting
INSERT INTO "SystemSettings" (setting_key, setting_value, description) 
VALUES ('log_level', 'INFO', 'Log level for the data collection pipeline: DEBUG, INFO, WARNING, ERROR, CRITICAL')
ON CONFLICT (setting_key) DO NOTHING;
