CREATE INDEX idx_option_history_osi_date 
ON "OptionDataMassiveHistoryDaily" (option_osi, snapshot_date) 
INCLUDE (day_close);