DROP VIEW IF EXISTS OptionPricingMetrics;
CREATE VIEW
    OptionPricingMetrics AS
SELECT
	*
FROM
	OptionPricingMetricsHistory
WHERE
	date = (
		SELECT
			MAX(date)
		FROM
			OptionPricingMetricsHistory
	);