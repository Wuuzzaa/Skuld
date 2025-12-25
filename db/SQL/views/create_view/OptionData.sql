DROP VIEW IF EXISTS OptionData;
CREATE VIEW
	OptionData AS
SELECT
	*
FROM
	OptionDataHistory
WHERE
	date = (
		SELECT
			MAX(date)
		FROM
			OptionDataHistory
	);