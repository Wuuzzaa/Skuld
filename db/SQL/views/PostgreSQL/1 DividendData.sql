DROP MATERIALIZED VIEW IF EXISTS "DividendData" CASCADE;

CREATE MATERIALIZED VIEW "DividendData" AS
WITH
	MEDIANDIVIDEND AS (
		SELECT
			SYMBOL,
			EXTRACT(
				YEAR
				FROM
					SNAPSHOT_DATE
			) AS DIV_YEAR,
			PERCENTILE_CONT(0.5) WITHIN GROUP (
				ORDER BY
					DIVIDENDS
			) AS MEDIAN_DIVIDEND
		FROM
			"StockPricesYahooHistoryDaily"
		WHERE
			DIVIDENDS > 0
		GROUP BY
			SYMBOL,
			DIV_YEAR
	),
	CLEANEDDATA AS (
		-- Schritt 1: Ausreißer entfernen. 
		-- Filtern gegen den Median -> Dividende darf nicht mehr als 25% vom Median abweichen
		SELECT
			A.SYMBOL,
			EXTRACT(
				YEAR
				FROM
					A.SNAPSHOT_DATE
			) AS DIV_YEAR,
			A.DIVIDENDS
		FROM
			"StockPricesYahooHistoryDaily" AS A
			INNER JOIN MEDIANDIVIDEND AS B ON A.SYMBOL = B.SYMBOL
			AND EXTRACT(
				YEAR
				FROM
					SNAPSHOT_DATE
			) = B.DIV_YEAR
		WHERE
			DIVIDENDS > 0
			AND ABS(
				(
					(DIVIDENDS - MEDIAN_DIVIDEND)::NUMERIC / NULLIF(MEDIAN_DIVIDEND, 0)
				) * 100
			) < 25
	),
	YEARLYSUMS AS (
		-- Schritt 2: Jährliche Summe bilden
		SELECT
			SYMBOL,
			DIV_YEAR,
			AVG(DIVIDENDS) AS ANNUAL_AVG_DIV
		FROM
			CLEANEDDATA
		GROUP BY
			SYMBOL,
			DIV_YEAR
	),
	GROWTHCHECK AS (
		-- Schritt 3: Vergleich mit dem Vorjahr
		SELECT
			SYMBOL,
			DIV_YEAR,
			ANNUAL_AVG_DIV,
			LAG(ANNUAL_AVG_DIV) OVER (
				PARTITION BY
					SYMBOL
				ORDER BY
					DIV_YEAR
			) AS PREV_YEAR_DIV,
			CASE
				WHEN ANNUAL_AVG_DIV > LAG(ANNUAL_AVG_DIV) OVER (
					PARTITION BY
						SYMBOL
					ORDER BY
						DIV_YEAR
				) THEN 1
				ELSE 0
			END AS IS_INCREASE
		FROM
			YEARLYSUMS
	),
	STREAKS AS (
		-- Schritt 4: Nur die Jahre zählen, die Teil der aktuellen ununterbrochenen Kette sind
		-- (Das ist ein vereinfachter Ansatz: Wir zählen alle Jahre seit dem letzten 'Drop')
		SELECT
			SYMBOL,
			COUNT(*) AS YEARS_OF_GROWTH
		FROM
			GROWTHCHECK
		WHERE
			DIV_YEAR > (
				SELECT
					COALESCE(MAX(DIV_YEAR), 0)
				FROM
					GROWTHCHECK GC2
				WHERE
					GC2.SYMBOL = GROWTHCHECK.SYMBOL
					AND GC2.IS_INCREASE = 0
			)
		GROUP BY
			SYMBOL
	)
	-- Finale Kategorisierung
SELECT
	symbol,
	years_of_growth,
	CASE
		WHEN YEARS_OF_GROWTH >= 25 THEN 'Dividend Champion'
		WHEN YEARS_OF_GROWTH >= 10 THEN 'Dividend Contender'
		WHEN YEARS_OF_GROWTH >= 5 THEN 'Dividend Challenger'
		ELSE 'None'
	END AS status
FROM
	STREAKS;

CREATE UNIQUE INDEX idx_dividend_symbol ON "DividendData" (symbol);