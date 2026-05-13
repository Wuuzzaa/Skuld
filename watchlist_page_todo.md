# Watchlist Page TODO

Dieses Dokument beschreibt die Anforderungen und das geplante Vorgehen für die Implementierung einer neuen "Watchlist"-Seite in Skuld.

## Zielsetzung
Das Ziel dieses Branches ist die Erweiterung von Skuld um eine Watchlist-Seite. Diese Seite soll es ermöglichen, eine Watchlist von Aktien-Symbolen zu verwalten (speichern, manipulieren, auswerten). Die Daten werden in einer Excel-Datei (`watchlist.xlsx`) gespeichert.

## Anforderungen
- **Speichermedium:** Eine Excel-Datei namens `watchlist.xlsx`.
- **Streamlit Integration:** 
    - Laden der Watchlist beim Öffnen der Seite.
    - Anzeige der Watchlist in der Streamlit App.
    - Speichern von Änderungen zurück in die Excel-Datei.
- **Datenstruktur (Spalten):**
    - `Symbol` (Ticker)
    - `Unternehmen` (Name des Unternehmens)
    - `timestamp` (Zeitpunkt der letzten Änderung/Hinzufügung)
    - `Person` (Wer hat den Eintrag erstellt/geändert - aktuell manuell, da kein Userhandling)
    - `Bemerkung` (Freitext)
    - `Level Kaufkurs 1`
    - `Level Kaufkurs 2`
    - `Level Kaufkurs 3`
    - `Level Verkaufkurs 1`
    - `Level Verkaufkurs 2`
    - `Level Verkaufkurs 3`
    - `Aktueller Kurs` (Live- oder zuletzt geladener Kurs)

## Geplantes Vorgehen
1.  **Initialisierung der Datenquelle:**
    - Erstellen einer initialen `watchlist.xlsx` im `data/` Verzeichnis (falls noch nicht vorhanden) mit den definierten Spaltenüberschriften.
2.  **Entwicklung der Streamlit-Seite (`pages/watchlist.py`):**
    - Implementierung einer Funktion zum Laden der Excel-Daten in ein Pandas DataFrame.
    - Implementierung einer Funktion zum Speichern des DataFrames zurück in die Excel-Datei.
    - Erstellung der UI-Komponenten:
        - `st.data_editor` zur direkten Bearbeitung der Watchlist.
        - Symbol-Eingabe mit Autocomplete/Validierung gegen die Datenbank (nur DB-Einträge valide).
        - Automatisches Update des `timestamp` bei jeder Änderung/Neuanlage einer Zeile.
        - Validierung auf Duplikate (Symbole dürfen nur einmal vorkommen).
        - Dropdown für das Feld `Person` (JL, DD, JP, JI, KK, MO).
        - Button zum Speichern der Änderungen.
3.  **Anbindung an Marktdaten & Formatierung (Nächster Schritt):**
    - Die aktuellen Kurse werden später aus der Datenbank bezogen.
    - Implementierung einer bedingten Formatierung (Styler):
        - Grün, wenn `Aktueller Kurs <= Kauflevel`.
        - Rot, wenn `Aktueller Kurs >= Verkaufslevel`.
4.  **Registrierung der Seite:**
    - Hinzufügen der neuen Seite `pages/watchlist.py` in der `app.py`.

## Fragen / Klärungsbedarf
- Keine weiteren Fragen aktuell. Die Umsetzung startet basierend auf den definierten Anforderungen.
