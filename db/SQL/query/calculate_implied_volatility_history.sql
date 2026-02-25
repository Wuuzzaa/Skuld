WITH
	DAILY_IV AS (
		WITH
			BESTDELTA AS (
				WITH
					HISTORY AS (
						SELECT
							A.SNAPSHOT_DATE AS DATE,
							B.SYMBOL,
							B.EXPIRATION_DATE,
							B.CONTRACT_TYPE,
							A.IMPLIED_VOLATILITY,
							A.GREEKS_DELTA
						FROM
							"OptionDataMassiveHistoryDaily" AS A
							JOIN "OptionDataMassiveMasterData" AS B ON A.OPTION_OSI = B.OPTION_OSI
							-- WHERE NOT EXISTS (
							-- 	SELECT 1 FROM "StockImpliedVolatilityMassiveHistoryDaily" AS C
							-- 	WHERE C.symbol = B.SYMBOL
							-- )
					),
					BESTEXPIRATIONS AS (
						-- Step 1: Find the single expiration date closest to 45 days for every symbol
						SELECT DISTINCT
							ON (DATE, SYMBOL) DATE,
							SYMBOL,
							EXPIRATION_DATE
						FROM
							HISTORY
						WHERE
							EXPIRATION_DATE::DATE > DATE
							AND EXTRACT(
								DOW
								FROM
									EXPIRATION_DATE::DATE
							) = 5 -- Es ist ein Freitag
							AND EXTRACT(
								DAY
								FROM
									EXPIRATION_DATE::DATE
							) BETWEEN 15 AND 21 -- Es ist der dritte Freitag
						ORDER BY
							DATE,
							SYMBOL,
							ABS((EXPIRATION_DATE::DATE - DATE) - 45) ASC
					)
					-- Step 2: From those specific dates, find the put and call closest to 0.5 delta
				SELECT DISTINCT
					ON (O.DATE, O.SYMBOL, O.CONTRACT_TYPE) O.DATE,
					O.SYMBOL,
					O.CONTRACT_TYPE,
					O.IMPLIED_VOLATILITY,
					O.GREEKS_DELTA,
					O.EXPIRATION_DATE
				FROM
					HISTORY O
					JOIN BESTEXPIRATIONS B ON O.DATE = B.DATE
					AND O.SYMBOL = B.SYMBOL
					AND O.EXPIRATION_DATE = B.EXPIRATION_DATE
				ORDER BY
					O.DATE,
					O.SYMBOL,
					O.CONTRACT_TYPE,
					ABS(ABS(O.GREEKS_DELTA) - 0.5) ASC
			)
			-- Step 3: Calculate the average vola from put and call
		SELECT
			DATE,
			SYMBOL,
			AVG(IMPLIED_VOLATILITY) AS IV
		FROM
			BESTDELTA
		GROUP BY
			DATE,
			SYMBOL
	),
	IV_STATS AS (
		SELECT
			DATE,
			SYMBOL,
			IV,
			-- Average, High und Low über 1 Jahr
			AVG(IV) OVER (
				PARTITION BY
					SYMBOL
				ORDER BY
					DATE ROWS BETWEEN 251 PRECEDING
					AND CURRENT ROW
			) AS IV_HIST,
			MAX(IV) OVER (
				PARTITION BY
					SYMBOL
				ORDER BY
					DATE ROWS BETWEEN 251 PRECEDING
					AND CURRENT ROW
			) AS IV_HIGH,
			MIN(IV) OVER (
				PARTITION BY
					SYMBOL
				ORDER BY
					DATE ROWS BETWEEN 251 PRECEDING
					AND CURRENT ROW
			) AS IV_LOW,
			-- Für Percentile benötigen wir die Verteilung (CUME_DIST gibt den Prozentsatz der Werte <= aktuellem Wert an)
			-- Ein präziser Workaround für ein rollendes Percentile ist ein Sub-Select oder eine Zählung:
			(
				SELECT
					COUNT(*)
				FROM
					DAILY_IV D2
				WHERE
					D2.SYMBOL = D1.SYMBOL
					AND D2.DATE < D1.DATE
					AND D2.DATE > D1.DATE - INTERVAL '1 year'
					AND D2.IV < D1.IV
			)::FLOAT / NULLIF(
				(
					SELECT
						COUNT(*)
					FROM
						DAILY_IV D2
					WHERE
						D2.SYMBOL = D1.SYMBOL
						AND D2.DATE < D1.DATE
						AND D2.DATE > D1.DATE - INTERVAL '1 year'
				),
				0
			) AS IV_PERCENTILE_ROLLING
		FROM
			DAILY_IV AS D1
	)
SELECT
	date AS snapshot_date,
	symbol,
	iv,
	iv_low,
	iv_high,
	-- IV Rank Formel: (Current - Low) / (High - Low) * 100
	CASE
		WHEN (iv_high - iv_low) = 0 THEN 0
		ELSE ((iv - iv_low) / (iv_high - iv_low)) * 100
	END AS IV_RANK,
	-- IV Percentile: Wie viel Prozent der Tage im letzten Jahr waren niedriger als heute?
	iv_percentile_rolling * 100 AS iv_percentile
FROM
	IV_STATS
ORDER BY
	symbol,
	date;