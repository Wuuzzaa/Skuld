DROP VIEW IF EXISTS StockData;
CREATE VIEW
    StockData AS
SELECT
	*
FROM
	StockDataHistory
WHERE
	date = (
		SELECT
			MAX(date)
		FROM
			StockDataHistory
	);