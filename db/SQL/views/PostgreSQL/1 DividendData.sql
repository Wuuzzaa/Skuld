DROP VIEW IF EXISTS "DividendData" CASCADE;
CREATE VIEW "DividendData" AS
WITH CleanedData AS (
    -- Schritt 1: Ausreißer entfernen. 
    -- Wir nehmen nur Dividenden an, die in einem "normalen" Bereich liegen (z.B. < 2.00$ pro Payout für MO).
    -- Alternativ: Filtern gegen den Median, falls deine DB das unterstützt.
    SELECT 
        symbol,
        EXTRACT(YEAR FROM SNAPSHOT_DATE) as div_year,
        dividends
    FROM "StockDayPricesYahooHistoryDaily"
    WHERE dividends > 0 
      AND dividends < 5 -- Filtert die 21.90 und 51.06 Ausreißer aus deinem Bild
),
YearlySums AS (
    -- Schritt 2: Jährliche Summe bilden
    SELECT 
        symbol,
        div_year,
        SUM(dividends) as annual_div
    FROM CleanedData
    GROUP BY symbol, div_year
),
GrowthCheck AS (
    -- Schritt 3: Vergleich mit dem Vorjahr
    SELECT 
        symbol,
        div_year,
        annual_div,
        LAG(annual_div) OVER (PARTITION BY symbol ORDER BY div_year) as prev_year_div,
        CASE WHEN annual_div > LAG(annual_div) OVER (PARTITION BY symbol ORDER BY div_year) THEN 1 ELSE 0 END as is_increase
    FROM YearlySums
),
Streaks AS (
    -- Schritt 4: Nur die Jahre zählen, die Teil der aktuellen ununterbrochenen Kette sind
    -- (Das ist ein vereinfachter Ansatz: Wir zählen alle Jahre seit dem letzten 'Drop')
    SELECT 
        symbol,
        COUNT(*) as years_of_growth
    FROM GrowthCheck
    WHERE div_year > (
        SELECT COALESCE(MAX(div_year), 0) 
        FROM GrowthCheck gc2 
        WHERE gc2.symbol = GrowthCheck.symbol AND gc2.is_increase = 0
    )
    GROUP BY symbol
)
-- Finale Kategorisierung
SELECT 
    symbol,
    years_of_growth,
    CASE 
        WHEN years_of_growth >= 25 THEN 'Dividend Champion'
        WHEN years_of_growth >= 10 THEN 'Dividend Contender'
        WHEN years_of_growth >= 5  THEN 'Dividend Challenger'
        ELSE 'None'
    END as status
FROM Streaks;