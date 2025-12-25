DROP TABLE IF EXISTS "AnalystPriceTargets";
CREATE TABLE "AnalystPriceTargets" (
	symbol TEXT PRIMARY KEY, 
	analyst_mean_target FLOAT
);