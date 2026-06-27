ALTER TABLE "EarningDates" 
    ALTER COLUMN "earnings_date" TYPE DATE 
        USING (
            CASE
				WHEN EARNINGS_DATE LIKE '%.%.%' THEN SUBSTR(EARNINGS_DATE, 7, 4) || '-' || SUBSTR(EARNINGS_DATE, 4, 2) || '-' || SUBSTR(EARNINGS_DATE, 1, 2)
				ELSE NULL
			END
        )::date;
ALTER TABLE "EarningDatesMasterData" 
    ALTER COLUMN "earnings_date" TYPE DATE 
        USING (
            CASE
				WHEN EARNINGS_DATE LIKE '%.%.%' THEN SUBSTR(EARNINGS_DATE, 7, 4) || '-' || SUBSTR(EARNINGS_DATE, 4, 2) || '-' || SUBSTR(EARNINGS_DATE, 1, 2)
				ELSE NULL
			END
        )::date;
ALTER TABLE "EarningDatesHistoryDaily" 
    ALTER COLUMN "earnings_date" TYPE DATE 
        USING (
            CASE
				WHEN EARNINGS_DATE LIKE '%.%.%' THEN SUBSTR(EARNINGS_DATE, 7, 4) || '-' || SUBSTR(EARNINGS_DATE, 4, 2) || '-' || SUBSTR(EARNINGS_DATE, 1, 2)
				ELSE NULL
			END
        )::date;
ALTER TABLE "EarningDatesHistoryWeekly" 
    ALTER COLUMN "earnings_date" TYPE DATE 
        USING (
            CASE
				WHEN EARNINGS_DATE LIKE '%.%.%' THEN SUBSTR(EARNINGS_DATE, 7, 4) || '-' || SUBSTR(EARNINGS_DATE, 4, 2) || '-' || SUBSTR(EARNINGS_DATE, 1, 2)
				ELSE NULL
			END
        )::date;
ALTER TABLE "EarningDatesHistoryMonthly" 
    ALTER COLUMN "earnings_date" TYPE DATE 
        USING (
            CASE
				WHEN EARNINGS_DATE LIKE '%.%.%' THEN SUBSTR(EARNINGS_DATE, 7, 4) || '-' || SUBSTR(EARNINGS_DATE, 4, 2) || '-' || SUBSTR(EARNINGS_DATE, 1, 2)
				ELSE NULL
			END
        )::date;