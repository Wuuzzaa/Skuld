import pandas as pd
import os
import shutil
import glob
import streamlit as st
import streamlit.components.v1 as components
import datetime
import urllib.parse
from src.database import select_into_dataframe_pg

# Konfiguration
WATCHLIST_FILE = "data/watchlist.xlsx"
BACKUP_DIR = "data/backups"
ANALYSES_DIR = "data/analyses"
PERSONS = ["JL", "DD", "JP", "JI", "KK", "MO"]
COLUMNS = [
    "Symbol",
    "Unternehmen",
    "Aktueller Kurs",
    "Person",
    "Bemerkung",
    "Level Kaufkurs 1",
    "Level Kaufkurs 2",
    "Level Kaufkurs 3",
    "Level Verkaufkurs 1",
    "Level Verkaufkurs 2",
    "Level Verkaufkurs 3",
    "timestamp",
]

SECTOR_TO_PROMPT_DICT = {
    "Basic Materials": "src/prompts/prompt_materials.txt",
    "Communication Services": "src/prompts/prompt_communication_services.txt",
    "Consumer Cyclical": "src/prompts/prompt_consumer_discretionary.txt",
    "Consumer Defensive": "src/prompts/prompt_consumer_staples.txt",
    "Energy": "src/prompts/prompt_energy.txt",
    "Financial Services": "src/prompts/prompt_financials.txt",
    "Healthcare": "src/prompts/prompt_health_care.txt",
    "Industrials": "src/prompts/prompt_industrials.txt",
    "Real Estate": "src/prompts/prompt_real_estate.txt",
    "Technology": "src/prompts/prompt_information_technology.txt",
    "Utilities": "src/prompts/prompt_utilities.txt",
}

def _get_sector_prompt(sector, symbol):
    """Lädt den sektorspezifischen Prompt und ersetzt [ZZZ] durch das Symbol."""
    if not sector or sector not in SECTOR_TO_PROMPT_DICT:
        return None
    filepath = SECTOR_TO_PROMPT_DICT[sector]
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                prompt = f.read()
            return prompt.replace("[ZZZ]", symbol)
    except Exception:
        pass
    return None

def _create_claude_prompt(row):
    symbol = row['Symbol']
    # Sektor wird später beim Laden der Daten hinzugefügt
    sector = row.get('sector')
    
    # Versuche sektorspezifischen Prompt
    sector_prompt = _get_sector_prompt(sector, symbol)
    if sector_prompt:
        encoded_prompt = urllib.parse.quote(sector_prompt.strip())
        return f'https://claude.ai/new?q={encoded_prompt}'

    return f"Fehler: Sektor '{sector}' nicht unterstützt"

def create_watchlist_backup():
    """Erstellt ein Backup der aktuellen Watchlist vor dem Speichern."""
    if not os.path.exists(WATCHLIST_FILE):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"watchlist_{timestamp}.xlsx")
    shutil.copy2(WATCHLIST_FILE, backup_path)


def list_backups():
    """Gibt eine Liste aller Backups zurück, sortiert nach Datum (neueste zuerst)."""
    if not os.path.exists(BACKUP_DIR):
        return []
    files = glob.glob(os.path.join(BACKUP_DIR, "watchlist_*.xlsx"))
    files.sort(key=os.path.getmtime, reverse=True)
    return files


def restore_backup(backup_path):
    """Stellt ein Backup wieder her. Erstellt vorher ein Sicherheits-Backup."""
    create_watchlist_backup()
    shutil.copy2(backup_path, WATCHLIST_FILE)


def get_analysis_path(symbol):
    """Gibt den Pfad zur Analyse-HTML-Datei für ein Symbol zurück."""
    return os.path.join(ANALYSES_DIR, f"{symbol}.html")


def has_analysis(symbol):
    """Prüft ob eine Analyse für das Symbol vorhanden ist."""
    return os.path.exists(get_analysis_path(symbol))


def save_analysis(symbol, html_content):
    """Speichert eine HTML-Analyse für ein Symbol."""
    os.makedirs(ANALYSES_DIR, exist_ok=True)
    path = get_analysis_path(symbol)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_content)


def delete_analysis(symbol):
    """Löscht die Analyse für ein Symbol."""
    path = get_analysis_path(symbol)
    if os.path.exists(path):
        os.remove(path)


def load_analysis(symbol):
    """Lädt den HTML-Inhalt einer Analyse."""
    path = get_analysis_path(symbol)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            df = pd.read_excel(WATCHLIST_FILE)
            # Sicherstellen, dass alle Spalten vorhanden sind
            for col in COLUMNS:
                if col not in df.columns:
                    df[col] = None
            return df[COLUMNS]
        except Exception as e:
            st.error(f"Fehler beim Laden der Watchlist: {e}")
            return pd.DataFrame(columns=COLUMNS)
    else:
        return pd.DataFrame(columns=COLUMNS)

def save_watchlist(df):
    """Speichert die Watchlist. Gibt True bei Erfolg zurück, False bei Fehler."""
    try:
        os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
        create_watchlist_backup()
        df.to_excel(WATCHLIST_FILE, index=False)
        # Verify file was actually written
        if not os.path.exists(WATCHLIST_FILE) or os.path.getsize(WATCHLIST_FILE) == 0:
            st.error("Fehler: Watchlist-Datei wurde nicht korrekt geschrieben!")
            return False
        return True
    except Exception as e:
        st.error(f"Fehler beim Speichern der Watchlist: {e}")
        return False

def update_watchlist_prices(df_watchlist, df_market_data):
    """Aktualisiert die Kurse und Unternehmensnamen in der Watchlist basierend auf den Marktdaten."""
    if df_watchlist.empty or df_market_data.empty:
        return df_watchlist, False
    
    # Erstelle Mapping für schnellen Zugriff
    market_map = df_market_data.set_index('symbol')[['live_stock_price', 'company_name']].to_dict('index')
    
    updated = False
    for idx, row in df_watchlist.iterrows():
        symbol = row['Symbol']
        if symbol in market_map:
            new_price = market_map[symbol]['live_stock_price']
            new_company = market_map[symbol]['company_name']
            
            if row['Aktueller Kurs'] != new_price or row['Unternehmen'] != new_company:
                df_watchlist.at[idx, 'Aktueller Kurs'] = new_price
                df_watchlist.at[idx, 'Unternehmen'] = new_company
                updated = True
                
    return df_watchlist, updated

@st.cache_data
def get_valid_symbols():
    try:
        # Versuche Symbole und Sektor aus der Datenbank zu laden
        df_symbols = select_into_dataframe_pg('select distinct symbol, live_stock_price, company_name, company_sector as sector from "OptionDataMerged" ORDER BY symbol ASC')
        if df_symbols is not None and not df_symbols.empty:
            return df_symbols
    except Exception as e:
        st.warning(f"Konnte Symbole nicht aus DB laden: {e}")
    return pd.DataFrame(columns=['symbol', 'live_stock_price', 'company_name', 'sector'])

def main():
    st.title("Watchlist")

    # Daten laden
    if 'watchlist_df' not in st.session_state:
        st.session_state.watchlist_df = load_watchlist()
    
    df_symbols = get_valid_symbols()
    valid_symbols = df_symbols['symbol'].tolist() if not df_symbols.empty else []

    # Marktpreise beim Laden der Seite aktualisieren
    if 'prices_updated' not in st.session_state:
        updated_df, was_updated = update_watchlist_prices(st.session_state.watchlist_df, df_symbols)
        if was_updated:
            st.session_state.watchlist_df = updated_df
        st.session_state.prices_updated = True

    # Sektor-Informationen zum Watchlist-DF hinzufügen für die Prompt-Generierung
    if not df_symbols.empty:
        sector_map = df_symbols.set_index('symbol')['sector'].to_dict()
        st.session_state.watchlist_df['sector'] = st.session_state.watchlist_df['Symbol'].map(sector_map)

    # Editor Setup
    column_config = {
        "Symbol": st.column_config.SelectboxColumn("Symbol", help="Aktien Ticker", required=True, options=valid_symbols),
        "Unternehmen": st.column_config.TextColumn("Unternehmen", disabled=True),
        "Person": st.column_config.SelectboxColumn("Person", options=PERSONS),
        "timestamp": st.column_config.DatetimeColumn("Zeitstempel", disabled=True),
        "Aktueller Kurs": st.column_config.NumberColumn("Aktueller Kurs", format="%.2f €", disabled=True),
        "Level Kaufkurs 1": st.column_config.NumberColumn("Kauf 1", format="%.2f €", min_value=0.0),
        "Level Kaufkurs 2": st.column_config.NumberColumn("Kauf 2", format="%.2f €", min_value=0.0),
        "Level Kaufkurs 3": st.column_config.NumberColumn("Kauf 3", format="%.2f €", min_value=0.0),
        "Level Verkaufkurs 1": st.column_config.NumberColumn("Verkauf 1", format="%.2f €", min_value=0.0),
        "Level Verkaufkurs 2": st.column_config.NumberColumn("Verkauf 2", format="%.2f €", min_value=0.0),
        "Level Verkaufkurs 3": st.column_config.NumberColumn("Verkauf 3", format="%.2f €", min_value=0.0),
    }

    # Data Editor
    # Apply conditional formatting for the display (read-only view for styling)
    def style_watchlist(df):
        def color_levels(row):
            styles = [''] * len(row)
            try:
                current_price = row['Aktueller Kurs']
                if pd.isna(current_price):
                    return styles
                
                # Farben für Kauflevel (Grün-Töne)
                # Kontrast optimiert für Darkmode: Dunklere Hintergründe mit weißer Schrift
                buy_colors = {
                    'Level Kaufkurs 1': 'background-color: #1e4620; color: white', # Dunkelgrün
                    'Level Kaufkurs 2': 'background-color: #155724; color: white', # Mittleres Grün
                    'Level Kaufkurs 3': 'background-color: #0b3d16; color: white'  # Sehr dunkles Grün
                }
                
                # Prüfe Kauflevel (von 3 nach 1, um das "beste" Level zuerst zu finden)
                for i in [3, 2, 1]:
                    col_name = f'Level Kaufkurs {i}'
                    val = row[col_name]
                    if not pd.isna(val):
                        try:
                            if float(current_price) <= float(val):
                                return [buy_colors[col_name]] * len(row)
                        except (ValueError, TypeError):
                            continue

                # Farben für Verkaufslevel (Rot-Töne)
                # Kontrast optimiert für Darkmode: Dunklere Hintergründe mit weißer Schrift
                sell_colors = {
                    'Level Verkaufkurs 1': 'background-color: #5c1a1a; color: white', # Dunkelrot
                    'Level Verkaufkurs 2': 'background-color: #721c24; color: white', # Mittleres Rot
                    'Level Verkaufkurs 3': 'background-color: #4d0b0b; color: white'  # Sehr dunkles Rot
                }

                # Prüfe Verkaufslevel (von 3 nach 1)
                for i in [3, 2, 1]:
                    col_name = f'Level Verkaufkurs {i}'
                    val = row[col_name]
                    if not pd.isna(val):
                        try:
                            if float(current_price) >= float(val):
                                return [sell_colors[col_name]] * len(row)
                        except (ValueError, TypeError):
                            continue
            except Exception as e:
                # Debug Info falls nötig
                # print(f"Error in color_levels: {e}")
                pass
            return styles

        # Währungsspalten definieren
        currency_cols = ["Aktueller Kurs", "Level Kaufkurs 1", "Level Kaufkurs 2", "Level Kaufkurs 3", 
                         "Level Verkaufkurs 1", "Level Verkaufkurs 2", "Level Verkaufkurs 3"]
        
        return df.style.apply(color_levels, axis=1).format({col: "{:.2f} €" for col in currency_cols}, na_rep="-")

    st.subheader("Aktuelle Watchlist")
    display_df = st.session_state.watchlist_df.copy()
    
    # Spalten für die Anzeige filtern (Sektor nicht anzeigen)
    display_cols = [c for c in display_df.columns if c != 'sector']
    st.dataframe(style_watchlist(display_df[display_cols]), width="stretch")

    # Claude KI Analyse Bereich
    if not st.session_state.watchlist_df.empty:
        watchlist_symbols = st.session_state.watchlist_df['Symbol'].dropna().unique().tolist()
        if watchlist_symbols:
            st.subheader("Claude KI Analyse & Berichte")
            col1, col2 = st.columns([2, 1])
            with col1:
                selected_symbol = st.selectbox("Symbol für Analyse auswählen", options=watchlist_symbols, key="analysis_symbol_select")
            
            if selected_symbol:
                # Hole die Zeile für das ausgewählte Symbol
                symbol_row = st.session_state.watchlist_df[st.session_state.watchlist_df['Symbol'] == selected_symbol].iloc[0]
                claude_url = _create_claude_prompt(symbol_row)
                
                with col2:
                    st.write("") # Padding
                    st.write("") # Padding
                    if "Fehler" in claude_url:
                        st.error(claude_url)
                    else:
                        st.link_button("Analyse in Claude öffnen", claude_url, use_container_width=True)
                
                # Integration der vorhandenen Analysen (HTML)
                if has_analysis(selected_symbol):
                    with st.expander(f"Vorhandenen Bericht für {selected_symbol} anzeigen", expanded=True):
                        html_content = load_analysis(selected_symbol)
                        if html_content:
                            components.html(html_content, height=800, scrolling=True)
                        
                        if st.button(f"Bericht für {selected_symbol} löschen", key="del_analysis_btn"):
                            delete_analysis(selected_symbol)
                            st.success(f"Bericht für {selected_symbol} gelöscht.")
                            st.rerun()
                
                # Upload Bereich innerhalb des Symbols
                with st.expander("Neuen Bericht (HTML) hochladen"):
                    uploaded_file = st.file_uploader(
                        f"HTML-Datei für **{selected_symbol}** auswählen",
                        type=["html", "htm"],
                        key="analysis_uploader",
                    )
                    if uploaded_file is not None:
                        if st.button("Bericht speichern", key="save_analysis_btn"):
                            html_content = uploaded_file.read().decode("utf-8")
                            save_analysis(selected_symbol, html_content)
                            st.success(f"Bericht für {selected_symbol} gespeichert!")
                            st.rerun()
        else:
            st.subheader("Claude KI Analyse")
            st.info("Keine Symbole in der Watchlist für Analyse verfügbar.")
    else:
        st.subheader("Claude KI Analyse")
        st.info("Watchlist ist leer.")

    st.subheader("Bearbeitungsmodus")

    edited_df = st.data_editor(
        st.session_state.watchlist_df[[c for c in st.session_state.watchlist_df.columns if c != 'sector']],
        column_config=column_config,
        num_rows="dynamic",
        width="stretch",
        key="watchlist_editor",
    )

    # Logik für Änderungen (Timestamp & Validierung)
    if st.button("Änderungen speichern"):
        # Leere Zeilen entfernen (ohne Symbol)
        edited_df = edited_df.dropna(subset=['Symbol']).reset_index(drop=True)

        # Validierung der Preis-Level
        for idx, row in edited_df.iterrows():
            k1 = row['Level Kaufkurs 1']
            k2 = row['Level Kaufkurs 2']
            k3 = row['Level Kaufkurs 3']
            v1 = row['Level Verkaufkurs 1']
            v2 = row['Level Verkaufkurs 2']
            v3 = row['Level Verkaufkurs 3']

            # Kauf 1 > Kauf 2 > Kauf 3
            if pd.notna(k1) and pd.notna(k2) and not (k1 > k2):
                st.error(f"Fehler in Zeile {idx + 1} ({row['Symbol']}): Kauf 1 ({k1}) muss größer als Kauf 2 ({k2}) sein.")
                return
            if pd.notna(k2) and pd.notna(k3) and not (k2 > k3):
                st.error(f"Fehler in Zeile {idx + 1} ({row['Symbol']}): Kauf 2 ({k2}) muss größer als Kauf 3 ({k3}) sein.")
                return

            # Verkauf 1 < Verkauf 2 < Verkauf 3
            if pd.notna(v1) and pd.notna(v2) and not (v1 < v2):
                st.error(f"Fehler in Zeile {idx + 1} ({row['Symbol']}): Verkauf 1 ({v1}) muss kleiner als Verkauf 2 ({v2}) sein.")
                return
            if pd.notna(v2) and pd.notna(v3) and not (v2 < v3):
                st.error(f"Fehler in Zeile {idx + 1} ({row['Symbol']}): Verkauf 2 ({v2}) muss kleiner als Verkauf 3 ({v3}) sein.")
                return

        # Vergleiche edited_df mit st.session_state.watchlist_df
        # Um den Timestamp zu setzen, prüfen wir auf Änderungen
        
        # Duplikate checken (nur nicht-leere Symbole)
        non_empty_symbols = edited_df['Symbol'].dropna()
        if non_empty_symbols[non_empty_symbols != ''].duplicated().any():
            st.error("Duplikate in den Symbolen gefunden! Jedes Symbol darf nur einmal vorkommen.")
            return

        # Validierung gegen DB Symbole (optional, falls valid_symbols nicht leer)
        if valid_symbols:
            invalid = edited_df[~edited_df['Symbol'].isin(valid_symbols)]['Symbol'].tolist()
            if invalid:
                st.warning(f"Folgende Symbole sind nicht in der Datenbank: {', '.join(invalid)}")

        # Timestamp für geänderte/neue Zeilen setzen
        now = datetime.datetime.now().replace(microsecond=0)
        
        # Wir vergleichen das ursprüngliche DF mit dem neuen.
        # Sektor aus ursprünglichem DF entfernen für Vergleich
        original_df_cmp = st.session_state.watchlist_df[[c for c in st.session_state.watchlist_df.columns if c != 'sector']]
        for idx in edited_df.index:
            if idx >= len(original_df_cmp):
                # Neue Zeile
                edited_df.loc[idx, 'timestamp'] = now
            else:
                # Bestehende Zeile - vergleiche Inhalt (ohne timestamp)
                # Wir konvertieren zu Strings für den Vergleich, um Typ-Probleme zu vermeiden
                original_row = original_df_cmp.iloc[idx].drop('timestamp', errors='ignore').fillna('').astype(str)
                new_row = edited_df.loc[idx].drop('timestamp', errors='ignore').fillna('').astype(str)
                if not original_row.equals(new_row):
                    edited_df.loc[idx, 'timestamp'] = now

        # Automatische Befüllung von Unternehmen und Kurs für neue/geänderte Symbole
        if not df_symbols.empty:
            symbol_map = df_symbols.set_index('symbol')
            for idx, row in edited_df.iterrows():
                symbol = row['Symbol']
                if pd.notna(symbol) and symbol in symbol_map.index:
                    db_row = symbol_map.loc[symbol]
                    # Update falls leer oder abweichend
                    if pd.isna(edited_df.at[idx, 'Unternehmen']) or edited_df.at[idx, 'Unternehmen'] == '':
                        edited_df.at[idx, 'Unternehmen'] = db_row['company_name']
                    if pd.isna(edited_df.at[idx, 'Aktueller Kurs']) or edited_df.at[idx, 'Aktueller Kurs'] == 0:
                        edited_df.at[idx, 'Aktueller Kurs'] = db_row['live_stock_price']
        
        st.session_state.watchlist_df = edited_df
        # Falls Sektor-Spalte fehlte (z.B. nach Save), wieder hinzufügen
        if 'sector' not in st.session_state.watchlist_df.columns and not df_symbols.empty:
            sector_map = df_symbols.set_index('symbol')['sector'].to_dict()
            st.session_state.watchlist_df['sector'] = st.session_state.watchlist_df['Symbol'].map(sector_map)

        if save_watchlist(edited_df[[c for c in edited_df.columns if c != 'sector']]):
            st.session_state.pop('prices_updated', None)  # Force price refresh on next load
            st.rerun()
        else:
            st.error("Speichern fehlgeschlagen! Daten wurden nicht persistiert.")

    # Automatischer Abgleich bei Symbolwahl (nach dem Save-Button damit kein rerun den Save blockiert)
    if "watchlist_editor" in st.session_state and not df_symbols.empty:
        changes = st.session_state.watchlist_editor
        symbol_map = df_symbols.set_index('symbol')
        any_auto_update = False

        # Geänderte Zeilen prüfen - nur NEUE Symbol-Änderungen triggern Auto-Fill
        for row_idx_str, edited_cols in changes.get('edited_rows', {}).items():
            if 'Symbol' in edited_cols:
                new_symbol = edited_cols['Symbol']
                if new_symbol in symbol_map.index:
                    row_idx = int(row_idx_str)
                    db_row = symbol_map.loc[new_symbol]
                    if row_idx < len(st.session_state.watchlist_df):
                        # Nur updaten wenn das Symbol sich wirklich geändert hat
                        current_symbol = st.session_state.watchlist_df.at[row_idx, 'Symbol']
                        if current_symbol != new_symbol:
                            st.session_state.watchlist_df.at[row_idx, 'Symbol'] = new_symbol
                            st.session_state.watchlist_df.at[row_idx, 'Unternehmen'] = db_row['company_name']
                            st.session_state.watchlist_df.at[row_idx, 'Aktueller Kurs'] = db_row['live_stock_price']
                            any_auto_update = True

        # Neue Zeilen prüfen (added_rows)
        if changes.get('added_rows'):
            new_rows = []
            for row in changes['added_rows']:
                if 'Symbol' in row:
                    new_symbol = row['Symbol']
                    if new_symbol in symbol_map.index:
                        db_row = symbol_map.loc[new_symbol]
                        new_entry = {col: None for col in COLUMNS}
                        new_entry.update(row)
                        new_entry['Unternehmen'] = db_row['company_name']
                        new_entry['Aktueller Kurs'] = db_row['live_stock_price']
                        new_entry['timestamp'] = datetime.datetime.now().replace(microsecond=0)
                        new_rows.append(new_entry)
                        any_auto_update = True

            if new_rows:
                st.session_state.watchlist_df = pd.concat([
                    st.session_state.watchlist_df,
                    pd.DataFrame(new_rows)
                ], ignore_index=True)

        if any_auto_update:
            # Editor-Key löschen um Endlosschleife zu verhindern
            del st.session_state["watchlist_editor"]
            st.rerun()

    # --- Backup & Restore Sektion ---
    with st.expander("Backup & Restore"):
        backups = list_backups()
        if backups:
            # Formatiere Backup-Namen für Anzeige
            backup_labels = []
            for b in backups:
                filename = os.path.basename(b)
                # watchlist_20260514_123456.xlsx -> 2026-05-14 12:34:56
                ts_str = filename.replace("watchlist_", "").replace(".xlsx", "")
                try:
                    ts = datetime.datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    backup_labels.append(ts.strftime("%Y-%m-%d %H:%M:%S"))
                except ValueError:
                    backup_labels.append(filename)

            selected_idx = st.selectbox(
                "Verfügbare Backups (max. 3 Tage)",
                range(len(backups)),
                format_func=lambda i: backup_labels[i],
                key="backup_select"
            )

            st.warning("Achtung: Die aktuelle Watchlist wird überschrieben! "
                       "Ein Sicherheits-Backup wird automatisch erstellt.")

            if st.button("Backup wiederherstellen"):
                restore_backup(backups[selected_idx])
                st.session_state.watchlist_df = load_watchlist()
                st.session_state.pop('prices_updated', None)
                st.success(f"Backup von {backup_labels[selected_idx]} wiederhergestellt!")
                st.rerun()
        else:
            st.info("Keine Backups vorhanden. Backups werden automatisch bei jedem Speichern erstellt.")


    # --- How-to-use Sektion ---
    with st.expander("ℹ️ How to use - Anleitung"):
        st.markdown("""
        ### Bedienungsanleitung für die Watchlist

        Diese Seite dient der Verwaltung und Überwachung deiner Aktientitel. Die Daten werden automatisch mit den aktuellen Marktpreisen aus der Datenbank abgeglichen.

        #### 1. Symbole hinzufügen & bearbeiten
        - Klicke im Editor unten auf die letzte Zeile, um ein **neues Symbol** hinzuzufügen.
        - Das Feld **Symbol** bietet eine Suche für alle in der Datenbank verfügbaren Titel.
        - Sobald ein Symbol ausgewählt wird, werden **Unternehmen** und **Aktueller Kurs** automatisch ergänzt.
        - Die Spalte **Person** bietet ein Dropdown mit den Kürzeln (JL, DD, JP, JI, KK, MO).

        #### 2. Preis-Levels setzen
        Du kannst bis zu drei Kauf- und Verkaufslevels definieren:
        - **Kauf-Levels:** Erwartung sinkender Kurse. Bedingung: `Kauf 1 > Kauf 2 > Kauf 3`.
        - **Verkauf-Levels:** Erwartung steigender Kurse. Bedingung: `Verkauf 1 < Verkauf 2 < Verkauf 3`.
        - Alle Werte müssen positive Zahlen sein.

        #### 3. Automatische Formatierung (Farben)
        Die obere Tabelle zeigt die Watchlist mit farblichen Hervorhebungen basierend auf dem aktuellen Marktkurs:
        - 🟢 **Grün:** Der aktuelle Kurs hat ein **Kauf-Level** erreicht oder unterschritten (`Kurs <= Level`).
        - 🔴 **Rot:** Der aktuelle Kurs hat ein **Verkauf-Level** erreicht oder überschritten (`Kurs >= Level`).
        - Je höher die Level-Stufe (z.B. Kauf 3), desto intensiver die Farbe.

        #### 4. Speichern
        - Änderungen im Editor werden erst dauerhaft in der `watchlist.xlsx` gespeichert, wenn du auf den Button **'Änderungen speichern'** klickst.
        - Dabei werden die Preis-Levels validiert und der **Zeitstempel** für geänderte Zeilen automatisch aktualisiert.

        #### 5. Aktualisierung
        - Beim Laden der Seite werden die Marktpreise automatisch aus der Datenbank aktualisiert.
        """)

if __name__ == "__main__":
    main()
