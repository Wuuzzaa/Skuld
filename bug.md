### Dokumentation: Analyse der Datenlücken bei Options-Spreads

**Datum:** 15. Mai 2026
**Thema:** Fehlende Symbole und Spread-Validierung in `OptionDataMerged`

---

#### 1. Zusammenfassung der Erkenntnisse
*   **Soll-Zustand:** 5.875 Symbole sind in `StockSymbolsMassive` mit `has_options = true` markiert.
*   **Ist-Zustand:** Nur 2.248 Symbole (~38%) weisen am gewählten Verfallstag (`expiration_date`) tatsächliche Optionsdaten auf.
*   **Differenz:** 3.627 Symbole fehlen am Stichtag komplett. Davon wurden ca. **3.448 Symbole noch nie** in der Tabelle `OptionDataMerged` erfasst.
*   **Schlussfolgerung:** Es liegt kein Fehler in der Spread-Logik oder den Liquiditätsfiltern vor. Das Problem ist die **Vollständigkeit des Daten-Feeds/Scrapers**, der nur eine Teilmenge des Universums abdeckt.

---

#### 2. Query zur Identifizierung fehlender Spreads
Diese Query zeigt Symbole, bei denen ein "Sell-Bein" gefunden wurde, aber der exakte Strike für das "Buy-Bein" (der Spread) im Orderbuch fehlt.

```sql
WITH FilteredOptions AS (
    SELECT symbol, expiration_date, contract_type AS option_type, strike_price AS strike
    FROM "OptionDataMerged"
    WHERE open_interest >= :min_open_interest AND day_volume >= :min_day_volume
),
TargetOptions AS (
    SELECT symbol, expiration_date, contract_type AS option_type, strike_price AS strike,
    CASE
        WHEN :strategy_type = 'credit' THEN
            CASE WHEN contract_type = 'put' THEN strike_price - :spread_width ELSE strike_price + :spread_width END
        ELSE
            CASE WHEN contract_type = 'put' THEN strike_price + :spread_width ELSE strike_price - :spread_width END
    END AS required_buy_strike,
    ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY abs(abs(greeks_delta) - :delta_target) ASC) as delta_rank
    FROM "OptionDataMerged"
    WHERE expiration_date = :expiration_date AND contract_type = :option_type
)
SELECT t.symbol, t.strike AS sell_strike, t.required_buy_strike,
       CASE WHEN b.strike IS NULL THEN 'FEHLT: Strike im Orderbuch nicht vorhanden' ELSE 'OK' END AS status
FROM TargetOptions t
LEFT JOIN FilteredOptions b ON t.symbol = b.symbol AND b.strike = t.required_buy_strike
WHERE t.delta_rank = 1 AND b.strike IS NULL;
```

---

#### 3. Lücken-Analyse (Cross-Check mit Master-Daten)
Diese Query vergleicht die Stammdaten mit den tatsächlich vorhandenen Marktdaten, um herauszufinden, warum Symbole "verschwinden".

```sql
WITH MasterSymbols AS (
    SELECT symbol FROM "StockSymbolsMassive" WHERE has_options = true
),
ExistingInOptionsData AS (
    SELECT symbol, count(DISTINCT expiration_date) as total_expirations
    FROM "OptionDataMerged" GROUP BY symbol
),
TargetDatePresence AS (
    SELECT DISTINCT symbol FROM "OptionDataMerged" WHERE expiration_date = :expiration_date
)
SELECT 
    m.symbol,
    CASE 
        WHEN e.symbol IS NULL THEN 'FEHLT KOMPLETT: Nie in OptionDataMerged gelandet'
        WHEN t.symbol IS NULL THEN 'DATUM FEHLT: In Tabelle vorhanden, aber nicht für diesen Termin'
        ELSE 'VORHANDEN'
    END AS daten_status
FROM MasterSymbols m
LEFT JOIN ExistingInOptionsData e ON m.symbol = e.symbol
LEFT JOIN TargetDatePresence t ON m.symbol = t.symbol
WHERE t.symbol IS NULL;
```

---

#### 4. Empfohlene nächste Schritte für die IT / Kollegen
1.  **Scraper-Scope prüfen:** Prüfen, ob der Scraper eine Limitierung hat (z.B. nur Top 2500 Symbole nach Marktkapitalisierung).
2.  **Import-Logs prüfen:** Gab es Abbrüche bei den 3.627 fehlenden Symbolen?
3.  **Strike-Intervalle:** Für die Symbole mit Status "FEHLT: Strike nicht vorhanden" sollte geprüft werden, ob die `spread_width` (z.B. 1.0) zu den Marktstandard-Intervallen des Symbols passt (viele Aktien haben nur 2.5 oder 5.0 Schritte).

---