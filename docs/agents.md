# Skuld - Systemarchitektur & Agenten-Verständnis

Skuld ist ein spezialisiertes Analyse-Tool für den Optionshandel, das darauf ausgelegt ist, große Mengen an Marktdaten (Aktien, Indizes, Optionsketten) zu sammeln, zu historisieren und über ein Flask-Frontend für strategische Entscheidungen (Spreads, Married Puts, etc.) aufzubereiten.

## Kernkomponenten

### 1. Daten-Pipeline (`main.py` & `src/`)
Die Pipeline ist das Herzstück von Skuld. Sie steuert die Datenbeschaffung aus verschiedenen Quellen und deren Transformation in die Datenbank.

- **Massive API (`src/massiv_api.py`):** 
    - Hauptquelle für Optionsketten, Griechen (Delta, Gamma, Theta, Vega) und Ticker-Informationen.
    - Unterscheidet zwischen `stock` (Aktien mit Exchange MIC wie XNAS, XNYS) und `index` (Indizes wie SPX ohne feste Börse).
    - Prüft die Verfügbarkeit von Optionen (`has_options`).
- **YahooQuery Scraper (`src/yahooquery_financials.py`, `src/live_stock_price_collector.py`):**
    - Liefert Fundamentaldaten, historische Kurse, Analysten-Kursziele, Dividenden und Asset-Profile (Sektor/Industrie).
- **Technische Indikatoren (`src/technical_indicators.py`):**
    - Berechnet Metriken auf Basis der gesammelten Preisdaten.
- **Implizite Volatilität (`src/stock_volatility.py`):**
    - Berechnet und speichert die IV auf Basis der Optionsdaten von Massive.

### 2. Datenbank-Schicht (`src/database.py` & `config.py`)
Skuld nutzt PostgreSQL als zentralen Datenspeicher.

- **Tabellen-Struktur:** Es gibt spezifische Tabellen für jeden Datentyp (z. B. `OptionDataMassive`, `StockPricesYahoo`, `AnalystPriceTargets`).
- **Historisierung (`src/historization.py`):** 
    - Ein dedizierter Mechanismus (`HISTORY_ENABLED_TABLES`), um Änderungen über die Zeit zu verfolgen.
- **Daten-Integrität:** `insert_into_table` und `insert_into_table_bulk` handhaben effiziente Schreibvorgänge und Loggen von Änderungen.

### 3. Frontend / UI (`app.py`, `flask_pages/` & `templates/`)
Skuld verwendet **Flask** (migriert von Streamlit) für eine interaktive Weboberfläche.

- **`app.py` (Main Entry Point):**
    - Erstellt die Flask-App und registriert alle Blueprints.
    - Injiziert globale Template-Variablen (z. B. `version`) via `@app.context_processor`.
    - Startet mit `python app.py` (Port 5000) oder `flask run`.
- **`flask_pages/` (Blueprint-Module):**
    - Jede Datei entspricht einer funktionalen Ansicht (z. B. `spreads.py`, `symbol_page.py`).
    - Blueprints lesen Filter-Parameter aus GET/POST-Requests, führen Datenbankabfragen durch und rendern Jinja2-Templates.
    - Neue Features als Blueprint in `flask_pages/` implementieren und in `app.py` registrieren.
- **`templates/` (Jinja2-Templates):**
    - `base.html`: Gemeinsames Layout mit Bootstrap 5, DataTables.js, Select2 und Navbar.
    - `templates/pages/`: Eine HTML-Datei pro Page.
- **`static/` (CSS & JS):**
    - `static/css/skuld.css`: Dark-Theme-Styling.
    - `static/js/skuld.js`: DataTables-Initialisierung für alle `.skuld-table`-Elemente.
- **`src/flask_table_helper.py`:**
    - Ersatz für das alte `src/page_display_dataframe.py`.
    - Konvertiert DataFrames in HTML-Tabellen mit TradingView-, Chart- und Claude-AI-Links.
    - Negative Zahlen werden rot markiert (`text-negative`).
- **Interaktive Module:**
    - **Analyst Prices** (`/analyst-prices/`): Vergleich von Kursen mit Analystenzielen.
    - **Spreads** (`/spreads/`): Spread-Kalkulator mit umfangreichen GET-Filtern.
    - **Married Puts** (`/married-puts/`): Married-Put-Analyse mit ROI/DTE/Dividend-Filtern.
    - **Position Insurance** (`/position-insurance/`): POST-Form für RadioActive Trading.
    - **Multifactor Swingtrading** (`/multifactor/`): Multifaktor-Strategie mit Percentile-Filtern.
    - **Sector Rotation** (`/sector-rotation/`): Plotly-Chart mit RS-Ratio/RS-Momentum.
    - **Expected Value** (`/expected-value/`): Monte-Carlo-Simulator mit dynamischen Options-Inputs.
    - **Symbol Page** (`/symbol/`): Fundamentaldaten, IV-History und technische Indikatoren pro Symbol.
    - **Data Logs** (`/data-logs/`): Einsicht in `DataChangeLogs`.

## Datenfluss (Workflow)

1.  **Initialisierung:** `load_symbols()` in `massiv_api.py` aktualisiert die Liste der handelbaren Symbole und Indizes.
2.  **Collection:** `main.py` startet verschiedene Jobs (z. B. `all`, `market_start_mid_end`, `option_data`) basierend auf Zeitplänen (Crontab).
3.  **Processing:** Rohdaten der APIs werden bereinigt, mit technischen Indikatoren angereichert und in die Datenbank geschrieben.
4.  **Historization:** Nach der Datensammlung wird der Historisierungsprozess angestoßen, um Zeitreihen-Analysen zu ermöglichen.
5.  **Visualization:** Der Nutzer greift über das Flask-Frontend auf die aggregierten und berechneten Daten zu.

## Konfiguration & Umgebung
- **`config.py`:** Zentrale Verwaltung von API-Keys, Datenbank-Verbindungen, Tabellennamen und globalen Parametern (z. B. Risk-Free-Rate, Simulation-Seeds).
- **Deployment:** Containerisierung via Docker (`docker-compose.yml`) für Datenbank und PgAdmin.
- **App starten:** `python app.py` oder `flask run --port 5000`

## Verständnis für Agenten (Summary)
Wenn du an Skuld arbeitest, beachte:
- **Typen-Strenge:** Achte auf die Unterscheidung zwischen `stock` und `index`.
- **API-Effizienz:** Nutze Batches und asynchrone Aufrufe (wie in `massiv_api.py` implementiert).
- **Daten-Historie:** Änderungen an Tabellen müssen oft im Historisierungs-Kontext betrachtet werden.
- **Blueprint-Navigation:** Neue Seiten als Blueprint in `flask_pages/` anlegen, Template in `templates/pages/` erstellen und Blueprint in `app.py` registrieren.
- **Datenbeschaffung in Pages:** Verwende `src/database.py` (z.B. `select_into_dataframe`) für SQL-Abfragen innerhalb der Blueprint-Routen.
- **Filter-Pattern:** GET-Parameter für Filter (Checkboxes, Inputs) mit Fallback auf `DEFAULTS`-Dict im Blueprint.
- **Tabellen-Rendering:** Nutze `src/flask_table_helper.py` → `dataframe_to_html()` für alle DataFrame-Ausgaben.
- **Zustands-Management:** Kein `st.session_state` mehr – Filter-Zustand wird über GET-Parameter in der URL gehalten.

## Junie (PyCharm Agent) Variante
Siehe [docs/junie.md](junie.md) für spezifische Arbeitsanweisungen und Workflows für den PyCharm-Agenten Junie.
