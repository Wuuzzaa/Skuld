DROP VIEW IF EXISTS OptionDataMerged;
CREATE VIEW OptionDataMerged AS
SELECT
	*
FROM
	OptionDataMergedHistory
WHERE
	date = (
		SELECT
			MAX(date)
		FROM
			OptionDataMergedHistory
	);