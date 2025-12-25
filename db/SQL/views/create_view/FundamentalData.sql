DROP VIEW IF EXISTS FundamentalData;
CREATE VIEW
	FundamentalData AS
SELECT
	*
FROM
	FundamentalDataHistory
WHERE
	date = (
		SELECT
			MAX(date)
		FROM
			FundamentalDataHistory
	);