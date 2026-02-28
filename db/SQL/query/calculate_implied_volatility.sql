WITH
	CURRENT_IV AS (
		WITH
			BESTDELTA AS (
				WITH
					BESTEXPIRATIONS AS (
						-- Step 1: Find the single expiration date closest to 45 days for every symbol
						SELECT DISTINCT
							ON (SYMBOL) SYMBOL,
							EXPIRATION_DATE
						FROM
							"OptionDataMassive"
						WHERE
							EXPIRATION_DATE::DATE > CURRENT_DATE
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
							SYMBOL,
							ABS((EXPIRATION_DATE::DATE - CURRENT_DATE) - 45) ASC
					)
					-- Step 2: From those specific dates, find the put and call closest to 0.5 delta
				SELECT DISTINCT
					ON (O.SYMBOL, O.CONTRACT_TYPE) O.SYMBOL,
					O.CONTRACT_TYPE,
					O.IMPLIED_VOLATILITY,
					O.GREEKS_DELTA,
					O.EXPIRATION_DATE
				FROM
					"OptionDataMassive" O
					JOIN BESTEXPIRATIONS B ON O.SYMBOL = B.SYMBOL
					AND O.EXPIRATION_DATE = B.EXPIRATION_DATE
				ORDER BY
					O.SYMBOL,
					O.CONTRACT_TYPE,
					ABS(ABS(O.GREEKS_DELTA) - 0.5) ASC
			)
			-- Step 3: Calculate the average vola from put and call
		SELECT
			SYMBOL,
			AVG(IMPLIED_VOLATILITY) AS IV
		FROM
			BESTDELTA
		GROUP BY
			SYMBOL
	),
	DAILY_IV AS (
		SELECT
			SNAPSHOT_DATE AS DATE,
			SYMBOL,
			IV
		FROM
			"StockImpliedVolatilityMassiveHistoryDaily"
		WHERE
			SNAPSHOT_DATE > CURRENT_DATE - INTERVAL '1 year'
	),
	IV_STATS AS (
		SELECT
			A.SYMBOL,
			-- High und Low über 1 Jahr
			MIN(CURRENT_IV) AS CURRENT_IV,
			MAX(GREATEST(IV, CURRENT_IV)) AS IV_HIGH,
			MIN(LEAST(IV, CURRENT_IV)) AS IV_LOW,
			SUM(CASE WHEN IV < CURRENT_IV THEN 1 ELSE 0 END) AS days_with_lower_iv,
			COUNT(*) AS trading_days
		FROM
			(
				SELECT
					SYMBOL,
					IV AS CURRENT_IV
				FROM
					CURRENT_IV
			) AS A 
			LEFT OUTER JOIN DAILY_IV AS B
			ON A.SYMBOL = B.SYMBOL
		GROUP BY
			A.SYMBOL,
			CURRENT_IV
	)
SELECT
	symbol,
	current_iv AS iv,
	iv_low,
	iv_high,
	-- IV Rank Formel: (Current - Low) / (High - Low) * 100
	CASE
		WHEN (iv_high - iv_low) = 0 THEN 0
		ELSE ((current_iv - iv_low) / (iv_high - iv_low)) * 100
	END AS iv_rank,
	-- IV Percentile: Wie viel Prozent der Tage im letzten Jahr waren niedriger als heute?
	(days_with_lower_iv::float/trading_days) * 100 AS iv_percentile
FROM
	iv_stats;