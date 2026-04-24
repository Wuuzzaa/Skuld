### Dokumentation: Spreads Page (Flask Portierung)

Dieses Dokument beschreibt die Funktionalität und die Elemente der Spreads-Seite in der Flask-Anwendung. Es dient als Grundlage für die Überprüfung der Umsetzung und die Planung weiterer Schritte.

---

### 1. Header & Titel
*   **Element:** Seitentitel "Spreads" mit Untertitel "Credit & debit spread scanner — delta-targeted, EV-filtered".
*   **Funktion:** Statische Anzeige zur Identifikation der Seite.

---

### 2. Filter-Leiste 1: Ablauf und Typ (Command Bar 1)

#### A. Expiry Chips (Monthly, Weekly, Daily)
*   **Element:** Drei anklickbare "Chips" (Checkboxen).
*   **Verhalten bei Klick:**
    *   Filtert die verfügbaren Ablaufdaten im darunterliegenden Dropdown.
    *   **Wichtig:** Setzt das aktuell ausgewählte Datum im Dropdown zurück (leert den Wert), um sicherzustellen, dass ein valider Wert für den neuen Filtertyp geladen wird.
    *   Die Seite wird automatisch neu geladen (`onchange`), um die Datumsliste zu aktualisieren.

#### B. Date Dropdown (Ablaufdatum)
*   **Element:** Ein Dropdown-Menü mit verfügbaren Ablaufdaten.
*   **Anzeige-Format:** `[DTE] DTE - [Wochentag] [Datum] - [Typ]` (z.B. "38 DTE - Friday 2026-05-22 - Monthly").
*   **Verhalten bei Auswahl:**
    *   Löst einen sofortigen Page-Submit aus.
    *   Lädt die Daten für das spezifische Datum aus der Datenbank.

#### C. Type Dropdown (Optionstyp)
*   **Element:** Dropdown zur Auswahl zwischen "Put" und "Call".
*   **Verhalten bei Auswahl:**
    *   Löst einen sofortigen Page-Submit aus.
    *   Wechselt die Strategie (Bull Put Spreads vs. Bear Call Spreads).

#### D. Quick Filters (+EV only, No earnings)
*   **Element:** Zwei Toggle-Chips (Checkboxen in Label-Wrapper).
    *   **+EV only:** Zeigt nur Spreads mit positivem Erwartungswert (Expected Value >= 0).
    *   **No earnings:** Filtert Symbole heraus, die ein Earnings-Event ab dem heutigen Datum bis zum Ablaufdatum haben.
*   **Verhalten bei Klick:** 
    *   Löst über eine Javascript-Funktion (`toggleChip`) einen sofortigen Page-Submit aus.
    *   Die Tabelle wird serverseitig gefiltert und die Seite neu gerendert.
    *   Der "Run"-Button ist für diese Filter nicht erforderlich.

---

### 3. Filter-Leiste 2: Numerische Parameter (Command Bar 2)

Diese Filter dienen der Feinjustierung der Strategie. Änderungen hier erfordern meist einen Klick auf den **"Run"** Button, um die Berechnung zu starten.

*   **Δ Target (Delta):** Ziel-Delta für die verkaufte Option (Standard: 0.20).
*   **Width $ (Spread Width):** Der Abstand zwischen verkauftem und gekauftem Strike (Standard: 5.0).
*   **Min Profit:** Mindestgewinn für den Spread (Credit).
*   **IV Range (min/max):** Filtert nach der Impliziten Volatilität der verkauften Option.
*   **IV Rank ≥:** Filtert nach dem IV Rank des Basiswerts.
*   **OI ≥ (Open Interest):** Mindestanzahl an offenen Kontrakten.
*   **Vol ≥ (Volume):** Mindesthandelsvolumen des Tages.

---

### 4. Aktions-Buttons

*   **Run (▶):** Führt die Berechnung mit allen aktuell gesetzten Parametern aus und aktualisiert die Tabelle.
*   **Reset:** Setzt alle Filter auf die Standardwerte zurück (Link zur Basis-URL der Spreads-Seite).

---

### 5. Statistik-Leiste (Stat Strip)
*   **Entfernt:** Die Statistik-Leiste wurde entfernt, da die Informationen bereits in den Filtern sichtbar sind.

---

### 6. Spreads Tabelle (Ergebnisliste)
Die Tabelle zeigt die berechneten Spreads an. Jede Zeile repräsentiert eine Strategie für ein Symbol.

#### Spalten-Erklärung:
*   **symbol:** Das Tickersymbol der Aktie.
*   **📊 / 📈 / 🔗 (Links):** Icons für externe Links zu TradingView (Profil und Chart) sowie OptionStrat. Öffnen sich in neuem Tab.
*   **🤖 (AI Analyse):** Link zu Claude AI. Generiert automatisch einen Prompt mit allen relevanten Daten des Spreads für eine KI-basierte Analyse.
*   **earnings_date:** Datum der nächsten Quartalszahlen.
*   **earnings_warning:** Ein Warnhinweis (z.B. "Earnings in 3 days"), falls relevant.
*   **close / analyst_mean_target:** Aktueller Kurs und durchschnittliches Analysten-Kursziel.
*   **iv_rank / iv_percentile:** Volatilitäts-Indikatoren.
*   **sell_strike / buy_strike:** Die Strikes des Spreads.
*   **sell_last_option_price / buy_last_option_price:** Letzte Preise der Optionen.
*   **max_profit:** Der maximale Gewinn (eingenommener Credit).
*   **bpr (Buying Power Reduction):** Das erforderliche Kapital/Risiko für diesen Trade.
*   **expected_value (EV):** Statistisch erwarteter Wert des Trades basierend auf Simulationen.
*   **APDI / APDI_EV:** Spezifische Kennzahlen zur Bewertung der Attraktivität des Spreads.

---

### 7. Interaktions-Logik (Zusammenfassung)

1.  **Automatisches Laden:** Beim Ändern von Ablaufdatum, Optionstyp oder Ablauf-Typen (Monthly etc.) wird die Seite meist sofort aktualisiert.
2.  **Manuelle Berechnung:** Numerische Filterwerte (Delta, Width etc.) werden erst durch Klick auf "Run" aktiv.
3.  **Fehlermeldungen:** Wenn keine Daten gefunden werden oder ein Datenbankfehler auftritt, wird eine entsprechende Info-Box (Alert) angezeigt.
