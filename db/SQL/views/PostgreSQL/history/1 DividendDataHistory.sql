DROP VIEW IF EXISTS "DividendDataHistory" CASCADE;

CREATE VIEW "DividendDataHistory" AS
SELECT
    A.DATE,
    A.SYMBOL,
    A.YEARS_OF_GROWTH AS DIVIDEND_GROWTH_YEARS,
    A.CLASSIFICATION AS DIVIDEND_CLASSIFICATION,
    B.LAST_DIVIDEND,
    B.LAST_DIVIDEND_DATE,
    C.NO_DIVIDEND_PAYOUTS_LAST_YEAR
FROM
    "DividendDataYahooHistory" AS A
    -- 1. LATERAL Join für die letzte Dividende vor/an dem jeweiligen historischen Datum (A.DATE)
    LEFT JOIN LATERAL (
        SELECT DISTINCT ON (SYMBOL) 
            SYMBOL,
            DIVIDENDS AS LAST_DIVIDEND,
            SNAPSHOT_DATE AS LAST_DIVIDEND_DATE
        FROM
            "StockPricesYahooHistoryDaily"
        WHERE
            SYMBOL = A.SYMBOL  -- Filterung direkt inside, da LATERAL das erlaubt
            AND DIVIDENDS > 0
            AND SNAPSHOT_DATE <= A.DATE  -- Es muss in der Vergangenheit (oder am selben Tag) liegen
            AND SNAPSHOT_DATE > A.DATE - INTERVAL '1 year'
        ORDER BY
            SYMBOL,
            SNAPSHOT_DATE DESC
    ) AS B ON TRUE -- Bei LATERAL wird die Bedingung oft nach innen verlagert, daher reicht ON TRUE
    
    -- 2. LATERAL Join für die Anzahl der Ausschüttungen im Jahr vor A.DATE
    LEFT JOIN LATERAL (
        SELECT
            COUNT(*) AS NO_DIVIDEND_PAYOUTS_LAST_YEAR
        FROM
            "StockPricesYahooHistoryDaily"
        WHERE
            SYMBOL = A.SYMBOL  -- Auch hier nutzen wir die Zuweisung direkt im Subquery
            AND DIVIDENDS > 0
            AND SNAPSHOT_DATE <= A.DATE
            AND SNAPSHOT_DATE > A.DATE - INTERVAL '1 year'
    ) AS C ON TRUE;