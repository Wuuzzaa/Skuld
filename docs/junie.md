# Skuld - Junie & Agent Guide

Diese Dokumentation dient als spezifischer Leitfaden für KI-Agenten (insbesondere Junie in PyCharm), die am Skuld-Projekt arbeiten. Sie ergänzt die `docs/agents.md` um operative Details und Best Practices für die automatisierte Code-Manipulation.

## Operative Prinzipien für Junie

### 1. Feature-Implementierung (Blueprint-Workflow)
Skuld ist modular über Flask-Blueprints aufgebaut. Wenn du eine neue Analyse-Seite oder Funktion hinzufügst:
- **Neuer Blueprint:** Erstelle eine neue Datei in `flask_pages/` (z.B. `new_feature.py`).
- **Standard-Filter:** Nutze das `DEFAULTS`-Dictionary und die `_get_params()` Funktion (siehe `spreads.py` als Vorlage), um Filter konsistent über GET-Parameter zu steuern.
- **Template-Struktur:** Erstelle das zugehörige HTML-Template in `templates/pages/`. Nutze `base.html` als Grundgerüst.
- **Registrierung:** Registriere den neuen Blueprint zwingend in `app.py`.

### 2. Datenzugriff & SQL
- **Keine direkten DB-Verbindungen:** Nutze immer die Abstraktionen in `src/database.py`.
- **`select_into_dataframe`:** Dies ist die bevorzugte Methode, um Daten für das Frontend abzurufen. Sie gibt einen Pandas DataFrame zurück, der leicht verarbeitet werden kann.
- **Query-Ordner:** SQL-Queries sollten idealerweise in `db/queries/` (falls vorhanden) oder als saubere Strings in der Blueprint-Datei liegen.
- **Typen-Sicherheit:** Achte bei Abfragen auf die Spaltennamen der PostgreSQL-Tabellen (siehe `src/database.py` für Tabellendefinitionen).

### 3. Frontend-Konventionen (DataTables & Styling)
- **Tabellen-Rendering:** Verwende `src/flask_table_helper.py` -> `dataframe_to_html(df)`. Dies fügt automatisch die notwendigen CSS-Klassen (`skuld-table`) hinzu.
- **Interaktivität:** Die `static/js/skuld.js` initialisiert automatisch DataTables für alle Tabellen mit der Klasse `.skuld-table`. Füge keine manuellen Initialisierungen in die Templates ein, außer für Spezialfälle.
- **Links & Formatierung:** Nutze die Helferfunktionen in `flask_table_helper.py`, um TradingView-Links oder farbliche Markierungen (rot für negativ) konsistent zu halten.

### 4. Daten-Pipeline & Scraper
- **`main.py` Erweiterung:** Wenn neue Datenquellen erschlossen werden, müssen diese in den `task_map` von `main.py` integriert werden, damit sie über den Crontab/Docker-Container laufen.
- **Historisierung:** Prüfe bei neuen Tabellen, ob sie in `src/historization.py` (`HISTORY_ENABLED_TABLES`) aufgenommen werden müssen, um Zeitreihen zu speichern.
- **Logging:** Nutze das vorhandene Logging-Setup (`setup_logging`). Logge wichtige Schritte in der Datenbeschaffung auf `DEBUG` oder `INFO` Ebene.

### 5. Testen & Verifizieren
- **Mocking:** Da das Projekt stark von externen APIs (Massive, Yahoo) abhängt, sollten Tests idealerweise Mocks verwenden oder auf der lokalen Test-Datenbank (`docker-compose.testing.yml`) operieren.
- **Linting:** Achte auf die Einhaltung der Python-Typisierung (Type Hints), wo sie bereits verwendet wird.

## Junie-spezifische Tools im Projekt
- **SQL-Analyse:** Nutze `sqlite3` für die `identifier.sqlite` (lokale Metadaten) oder entsprechende CLI-Tools für die PostgreSQL-Datenbank im Docker-Verbund.
- **Terminal:** Befehle sollten immer im Kontext der Docker-Umgebung gedacht werden (z.B. `docker-compose exec app ...`), wenn sie die Live-Datenbank betreffen.

## Zusammenfassung für schnelle Tasks
1. **Analysiere** die bestehende Logik in `flask_pages/` oder `src/`.
2. **Implementiere** minimalinvasiv.
3. **Registriere** Blueprints in `app.py`.
4. **Verifiziere** durch Aufruf der Route (Port 5000).
