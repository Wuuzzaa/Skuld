import pandas as pd
import os
import shutil
import glob
import streamlit as st
import streamlit.components.v1 as components
import datetime
import urllib.parse
from src.database import select_into_dataframe

# Projekt-Basisverzeichnis ermitteln
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Konfiguration
WATCHLIST_FILE = os.path.join(BASE_DIR, "data", "watchlist.xlsx")
BACKUP_DIR = os.path.join(BASE_DIR, "data", "backups")
ANALYSES_DIR = os.path.join(BASE_DIR, "data", "analyses")
PERSONS = ["JL", "DD", "JP", "JI", "KK", "MO"]
COLUMNS = [
    "Symbol",
    "Unternehmen",
    "Kategorie",
    "Aktueller Kurs",
    "Kurs Watchlistanlage",
    "Kursänderung",
    "Person",
    "Bemerkung",
    "Stop Loss",
    "Einstieg 1",
    "Einstieg 2",
    "Einstieg 3",
    "Take Profit 1",
    "Take Profit 2",
    "Take Profit 3",
    "timestamp",
]

SECTOR_TO_PROMPT_DICT = {
    "Basic Materials": os.path.join(BASE_DIR, "src", "prompts", "prompt_materials.txt"),
    "Communication Services": os.path.join(BASE_DIR, "src", "prompts", "prompt_communication_services.txt"),
    "Consumer Cyclical": os.path.join(BASE_DIR, "src", "prompts", "prompt_consumer_discretionary.txt"),
    "Consumer Defensive": os.path.join(BASE_DIR, "src", "prompts", "prompt_consumer_staples.txt"),
    "Energy": os.path.join(BASE_DIR, "src", "prompts", "prompt_energy.txt"),
    "Financial Services": os.path.join(BASE_DIR, "src", "prompts", "prompt_financials.txt"),
    "Healthcare": os.path.join(BASE_DIR, "src", "prompts", "prompt_health_care.txt"),
    "Industrials": os.path.join(BASE_DIR, "src", "prompts", "prompt_industrials.txt"),
    "Real Estate": os.path.join(BASE_DIR, "src", "prompts", "prompt_real_estate.txt"),
    "Technology": os.path.join(BASE_DIR, "src", "prompts", "prompt_information_technology.txt"),
    "Utilities": os.path.join(BASE_DIR, "src", "prompts", "prompt_utilities.txt"),
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
    sector = row.get('Sektor')
    
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
    # Cleanup: Backups älter als 14 Tage löschen
    cleanup_old_backups(max_age_days=14)


def cleanup_old_backups(max_age_days=14):
    """Löscht Backups die älter als max_age_days sind."""
    if not os.path.exists(BACKUP_DIR):
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=max_age_days)
    for f in glob.glob(os.path.join(BACKUP_DIR, "watchlist_*.xlsx")):
        if os.path.getmtime(f) < cutoff.timestamp():
            os.remove(f)


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
            
            # Explizite Typ-Konvertierung für Text-Spalten zur Vermeidung von Streamlit-Fehlern
            text_columns = ["Symbol", "Unternehmen", "Kategorie", "Person", "Bemerkung"]
            for col in text_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace(['nan', 'None', '<NA>'], '')

            # Numerische Spalten initialisieren falls nötig
            numeric_columns = [
                "Aktueller Kurs", "Kurs Watchlistanlage", "Kursänderung", 
                "Stop Loss", "Einstieg 1", "Einstieg 2", "Einstieg 3", 
                "Take Profit 1", "Take Profit 2", "Take Profit 3"
            ]
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
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
            
            # Kursänderung berechnen, falls Anlagekurs vorhanden
            if 'Kurs Watchlistanlage' in row and pd.notna(row['Kurs Watchlistanlage']) and row['Kurs Watchlistanlage'] != 0:
                change = ((new_price / row['Kurs Watchlistanlage']) - 1) * 100
                if pd.isna(row['Kursänderung']) or abs(row['Kursänderung'] - change) > 0.001:
                    df_watchlist.at[idx, 'Kursänderung'] = change
                    updated = True

            if row['Aktueller Kurs'] != new_price or row['Unternehmen'] != new_company:
                df_watchlist.at[idx, 'Aktueller Kurs'] = new_price
                df_watchlist.at[idx, 'Unternehmen'] = new_company
                updated = True
                
    return df_watchlist, updated

@st.cache_data(ttl=3600)
def get_valid_symbols():
    try:
        # Versuche Symbole und Sektor aus der Datenbank zu laden
        df_symbols = select_into_dataframe('select distinct symbol, live_stock_price, company_name, company_sector as "Sektor" from "OptionDataMerged" ORDER BY symbol ASC')
        if df_symbols is not None and not df_symbols.empty:
            return df_symbols
    except Exception as e:
        st.warning(f"Konnte Symbole nicht aus DB laden: {e}")
    return pd.DataFrame(columns=['symbol', 'live_stock_price', 'company_name', 'Sektor'])

def main():
    st.title("Watchlist")

    # Daten laden
    if 'watchlist_df' not in st.session_state:
        st.session_state.watchlist_df = load_watchlist()
    
    df_symbols = get_valid_symbols()
    valid_symbols = df_symbols['symbol'].tolist() if not df_symbols.empty else []
    valid_companies = df_symbols['company_name'].tolist() if not df_symbols.empty else []

    # Marktpreise beim Laden der Seite aktualisieren
    if 'prices_updated' not in st.session_state:
        updated_df, was_updated = update_watchlist_prices(st.session_state.watchlist_df, df_symbols)
        if was_updated:
            st.session_state.watchlist_df = updated_df
        st.session_state.prices_updated = True

    # Sektor-Informationen zum Watchlist-DF hinzufügen für die Prompt-Generierung
    if not df_symbols.empty:
        sector_map = df_symbols.set_index('symbol')['Sektor'].to_dict()
        st.session_state.watchlist_df['Sektor'] = st.session_state.watchlist_df['Symbol'].map(sector_map).fillna('').astype(str)
        
        # Spaltenreihenfolge anpassen: Sektor nach Unternehmen
        cols = list(st.session_state.watchlist_df.columns)
        if 'Sektor' in cols and 'Unternehmen' in cols:
            cols.remove('Sektor')
            idx = cols.index('Unternehmen') + 1
            cols.insert(idx, 'Sektor')
            st.session_state.watchlist_df = st.session_state.watchlist_df[cols]

    # Editor Setup
    column_config = {
        "Symbol": st.column_config.SelectboxColumn("Symbol", help="Aktien Ticker", options=valid_symbols),
        "Unternehmen": st.column_config.SelectboxColumn("Unternehmen", help="Name des Unternehmens", options=valid_companies),
        "Kategorie": st.column_config.TextColumn("Kategorie", help="Freitext Kategorie"),
        "Sektor": st.column_config.TextColumn("Sektor", disabled=True),
        "Aktueller Kurs": st.column_config.NumberColumn("Aktueller Kurs", format="%.2f €", disabled=True),
        "Kurs Watchlistanlage": st.column_config.NumberColumn("Kurs Anlage", format="%.2f €", help="Kurs bei Anlage"),
        "Kursänderung": st.column_config.NumberColumn("Änderung %", format="%.2f %%", disabled=True),
        "Person": st.column_config.SelectboxColumn("Person", options=PERSONS),
        "timestamp": st.column_config.DatetimeColumn("Zeitstempel", disabled=True),
        "Stop Loss": st.column_config.NumberColumn("Stop Loss", format="%.2f €", min_value=0.0),
        "Einstieg 1": st.column_config.NumberColumn("Einstieg 1", format="%.2f €", min_value=0.0),
        "Einstieg 2": st.column_config.NumberColumn("Einstieg 2", format="%.2f €", min_value=0.0),
        "Einstieg 3": st.column_config.NumberColumn("Einstieg 3", format="%.2f €", min_value=0.0),
        "Take Profit 1": st.column_config.NumberColumn("TP1", format="%.2f €", min_value=0.0),
        "Take Profit 2": st.column_config.NumberColumn("TP2", format="%.2f €", min_value=0.0),
        "Take Profit 3": st.column_config.NumberColumn("TP3", format="%.2f €", min_value=0.0),
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
                
                current_price = float(current_price)

                # 1. Stop Loss: Kurs < Stop Loss -> Rot
                sl_val = row['Stop Loss']
                if pd.notna(sl_val) and sl_val != '':
                    try:
                        if current_price < float(sl_val):
                            return ['background-color: #5c1a1a; color: white'] * len(row)
                    except (ValueError, TypeError):
                        pass

                # 2. Einstieg: Kurs <= Einstieg -> Blau
                # Wir prüfen von E3 zu E1 (falls mehrere erreicht sind, nehmen wir das "tiefste" Blau)
                for i in [3, 2, 1]:
                    col_name = f'Einstieg {i}'
                    val = row[col_name]
                    if pd.notna(val) and val != '':
                        try:
                            if current_price <= float(val):
                                # Blau-Töne für Einstieg
                                blue_colors = {
                                    'Einstieg 1': 'background-color: #004085; color: white',
                                    'Einstieg 2': 'background-color: #003366; color: white',
                                    'Einstieg 3': 'background-color: #002244; color: white'
                                }
                                return [blue_colors[col_name]] * len(row)
                        except (ValueError, TypeError):
                            continue

                # 3. Take Profit: Kurs >= Take Profit -> Grün
                for i in [3, 2, 1]:
                    col_name = f'Take Profit {i}'
                    val = row[col_name]
                    if pd.notna(val) and val != '':
                        try:
                            if current_price >= float(val):
                                # Grün-Töne für Take Profit
                                green_colors = {
                                    'Take Profit 1': 'background-color: #1e4620; color: white',
                                    'Take Profit 2': 'background-color: #155724; color: white',
                                    'Take Profit 3': 'background-color: #0b3d16; color: white'
                                }
                                return [green_colors[col_name]] * len(row)
                        except (ValueError, TypeError):
                            continue

            except Exception:
                pass
            return styles

        # Währungsspalten definieren
        currency_cols = ["Aktueller Kurs", "Kurs Watchlistanlage", "Stop Loss", "Einstieg 1", "Einstieg 2", "Einstieg 3", 
                         "Take Profit 1", "Take Profit 2", "Take Profit 3"]
        
        return df.style.apply(color_levels, axis=1).format({col: "{:.2f} €" for col in currency_cols} | {"Kursänderung": "{:.2f} %"}, na_rep="-")

    st.subheader("Aktuelle Watchlist")
    
    # Filter-Sektion
    with st.expander("🔍 Filter", expanded=False):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        
        # Verfügbare Werte für Filter sammeln
        avail_symbols = sorted(st.session_state.watchlist_df['Symbol'].dropna().unique().tolist())
        avail_companies = sorted(st.session_state.watchlist_df['Unternehmen'].dropna().unique().tolist())
        avail_persons = sorted(st.session_state.watchlist_df['Person'].dropna().unique().tolist())
        avail_categories = sorted(st.session_state.watchlist_df['Kategorie'].dropna().unique().tolist())
        
        with f_col1:
            filter_symbol = st.multiselect("Symbol", options=avail_symbols)
        with f_col2:
            filter_company = st.multiselect("Unternehmen", options=avail_companies)
        with f_col3:
            filter_person = st.multiselect("Person", options=avail_persons)
        with f_col4:
            filter_category = st.multiselect("Kategorie", options=avail_categories)

    display_df = st.session_state.watchlist_df.copy()
    
    # Filter anwenden
    if filter_symbol:
        display_df = display_df[display_df['Symbol'].isin(filter_symbol)]
    if filter_company:
        display_df = display_df[display_df['Unternehmen'].isin(filter_company)]
    if filter_person:
        display_df = display_df[display_df['Person'].isin(filter_person)]
    if filter_category:
        display_df = display_df[display_df['Kategorie'].isin(filter_category)]
    
    # Spalten für die Anzeige (Sektor anzeigen)
    st.dataframe(style_watchlist(display_df), column_config=column_config, width="stretch")

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
                        st.link_button("Analyse in Claude öffnen", claude_url, width="stretch")
                
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

    # Vor der Bearbeitung sicherstellen, dass Textspalten wirklich Strings sind
    # Dies verhindert StreamlitAPIException bei inkompatiblen Typen (z.B. Kategorie als Float)
    for col in ["Symbol", "Unternehmen", "Kategorie", "Person", "Bemerkung", "Sektor"]:
        if col in st.session_state.watchlist_df.columns:
            st.session_state.watchlist_df[col] = st.session_state.watchlist_df[col].astype(str).replace(['nan', 'None', '<NA>'], '')

    edited_df = st.data_editor(
        st.session_state.watchlist_df,
        column_config=column_config,
        num_rows="dynamic",
        width="stretch",
        key="watchlist_editor",
    )

    # Logik für Änderungen (Timestamp & Validierung)
    if st.button("Änderungen speichern"):
        # Leere Zeilen entfernen (ohne Symbol)
        edited_df = edited_df.dropna(subset=['Symbol']).reset_index(drop=True)

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
        original_df_cmp = st.session_state.watchlist_df[[c for c in st.session_state.watchlist_df.columns if c != 'Sektor']]
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
                    
                    # Initialen Kurs für Watchlistanlage setzen, falls noch nicht vorhanden
                    if pd.isna(edited_df.at[idx, 'Kurs Watchlistanlage']) or edited_df.at[idx, 'Kurs Watchlistanlage'] == 0:
                        edited_df.at[idx, 'Kurs Watchlistanlage'] = db_row['live_stock_price']
        
        st.session_state.watchlist_df = edited_df
        # Falls Sektor-Spalte fehlte (z.B. nach Save), wieder hinzufügen
        if 'Sektor' not in st.session_state.watchlist_df.columns and not df_symbols.empty:
            sector_map = df_symbols.set_index('symbol')['Sektor'].to_dict()
            st.session_state.watchlist_df['Sektor'] = st.session_state.watchlist_df['Symbol'].map(sector_map)

        # Validierung der Preis-Logik
        errors = []
        for idx, row in edited_df.iterrows():
            symbol = row.get('Symbol', f"Zeile {idx+1}")
            sl = row.get('Stop Loss')
            e1 = row.get('Einstieg 1')
            e2 = row.get('Einstieg 2')
            e3 = row.get('Einstieg 3')
            tp1 = row.get('Take Profit 1')
            tp2 = row.get('Take Profit 2')
            tp3 = row.get('Take Profit 3')

            # Hilfsfunktion zum sicheren Vergleich
            def is_less(a, b):
                if pd.isna(a) or pd.isna(b): return True
                return float(a) < float(b)

            # Validierung: Stop Loss < Einstieg 1 < Take Profit 1
            if not is_less(sl, e1):
                errors.append(f"{symbol}: Stop Loss ({sl}) muss kleiner als Einstieg 1 ({e1}) sein.")
            if not is_less(e1, tp1):
                errors.append(f"{symbol}: Einstieg 1 ({e1}) muss kleiner als Take Profit 1 ({tp1}) sein.")

            # Validierung: E1 < E2 < E3
            if not is_less(e1, e2):
                errors.append(f"{symbol}: Einstieg 1 ({e1}) muss kleiner als Einstieg 2 ({e2}) sein.")
            if not is_less(e2, e3):
                errors.append(f"{symbol}: Einstieg 2 ({e2}) muss kleiner als Einstieg 3 ({e3}) sein.")

            # Validierung: TP1 < TP2 < TP3
            if not is_less(tp1, tp2):
                errors.append(f"{symbol}: Take Profit 1 ({tp1}) muss kleiner als Take Profit 2 ({tp2}) sein.")
            if not is_less(tp2, tp3):
                errors.append(f"{symbol}: Take Profit 2 ({tp2}) muss kleiner als Take Profit 3 ({tp3}) sein.")

        if errors:
            for err in errors:
                st.error(err)
            return

        if save_watchlist(edited_df[[c for c in edited_df.columns if c != 'Sektor']]):
            st.session_state.pop('prices_updated', None)  # Force price refresh on next load
            st.rerun()
        else:
            st.error("Speichern fehlgeschlagen! Daten wurden nicht persistiert.")

    # Automatischer Abgleich bei Symbolwahl oder Unternehmenswahl
    if "watchlist_editor" in st.session_state and not df_symbols.empty:
        changes = st.session_state.watchlist_editor
        symbol_map = df_symbols.set_index('symbol')
        company_map = df_symbols.set_index('company_name')
        any_auto_update = False

        # Geänderte Zeilen prüfen
        for row_idx_str, edited_cols in changes.get('edited_rows', {}).items():
            row_idx = int(row_idx_str)
            if row_idx >= len(st.session_state.watchlist_df):
                continue
                
            if 'Symbol' in edited_cols:
                new_symbol = edited_cols['Symbol']
                if new_symbol in symbol_map.index:
                    db_row = symbol_map.loc[new_symbol]
                    # Nur updaten wenn das Symbol sich wirklich geändert hat
                    current_symbol = st.session_state.watchlist_df.at[row_idx, 'Symbol']
                    if current_symbol != new_symbol:
                        st.session_state.watchlist_df.at[row_idx, 'Symbol'] = new_symbol
                        st.session_state.watchlist_df.at[row_idx, 'Unternehmen'] = db_row['company_name']
                        st.session_state.watchlist_df.at[row_idx, 'Aktueller Kurs'] = db_row['live_stock_price']
                    
                        # Initialen Kurs setzen
                        if pd.isna(st.session_state.watchlist_df.at[row_idx, 'Kurs Watchlistanlage']) or st.session_state.watchlist_df.at[row_idx, 'Kurs Watchlistanlage'] == 0:
                            st.session_state.watchlist_df.at[row_idx, 'Kurs Watchlistanlage'] = db_row['live_stock_price']
                    
                        any_auto_update = True
            
            elif 'Unternehmen' in edited_cols:
                new_company = edited_cols['Unternehmen']
                if new_company in company_map.index:
                    db_row = company_map.loc[new_company]
                    # Nur updaten wenn das Unternehmen sich wirklich geändert hat
                    current_company = st.session_state.watchlist_df.at[row_idx, 'Unternehmen']
                    if current_company != new_company:
                        st.session_state.watchlist_df.at[row_idx, 'Unternehmen'] = new_company
                        st.session_state.watchlist_df.at[row_idx, 'Symbol'] = db_row['symbol']
                        st.session_state.watchlist_df.at[row_idx, 'Aktueller Kurs'] = db_row['live_stock_price']
                    
                        # Initialen Kurs setzen
                        if pd.isna(st.session_state.watchlist_df.at[row_idx, 'Kurs Watchlistanlage']) or st.session_state.watchlist_df.at[row_idx, 'Kurs Watchlistanlage'] == 0:
                            st.session_state.watchlist_df.at[row_idx, 'Kurs Watchlistanlage'] = db_row['live_stock_price']
                    
                        any_auto_update = True

        # Neue Zeilen prüfen (added_rows)
        if changes.get('added_rows'):
            new_rows_to_add = []
            for row in changes['added_rows']:
                new_entry = {col: None for col in COLUMNS}
                new_entry.update(row)
                
                if 'Symbol' in row and row['Symbol'] in symbol_map.index:
                    db_row = symbol_map.loc[row['Symbol']]
                    new_entry['Unternehmen'] = db_row['company_name']
                    new_entry['Aktueller Kurs'] = db_row['live_stock_price']
                    new_entry['Kurs Watchlistanlage'] = db_row['live_stock_price']
                    new_entry['timestamp'] = datetime.datetime.now().replace(microsecond=0)
                    new_rows_to_add.append(new_entry)
                    any_auto_update = True
                elif 'Unternehmen' in row and row['Unternehmen'] in company_map.index:
                    db_row = company_map.loc[row['Unternehmen']]
                    new_entry['Symbol'] = db_row['symbol']
                    new_entry['Aktueller Kurs'] = db_row['live_stock_price']
                    new_entry['Kurs Watchlistanlage'] = db_row['live_stock_price']
                    new_entry['timestamp'] = datetime.datetime.now().replace(microsecond=0)
                    new_rows_to_add.append(new_entry)
                    any_auto_update = True

            if new_rows_to_add:
                new_df = pd.DataFrame(new_rows_to_add)
                # Sicherstellen, dass alle Spalten aus watchlist_df vorhanden sind
                for col in st.session_state.watchlist_df.columns:
                    if col not in new_df.columns:
                        new_df[col] = None
                
                # Spaltenreihenfolge angleichen
                new_df = new_df[st.session_state.watchlist_df.columns]
                
                # Vor der Verkettung leere/NA-Einträge bereinigen, falls sie Probleme machen
                # Aber eigentlich reicht es, wenn die Spalten existieren.
                # Um die FutureWarning zu vermeiden:
                if not new_df.empty:
                    st.session_state.watchlist_df = pd.concat([
                        st.session_state.watchlist_df,
                        new_df
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
        - Klicke im **Bearbeitungsmodus** (unten) auf die letzte Zeile, um ein **neues Symbol** hinzuzufügen.
        - Das Feld **Symbol** bietet eine Suche für alle in der Datenbank verfügbaren Titel.
        - Sobald ein Symbol ausgewählt wird, werden **Unternehmen**, **Sektor** und **Aktueller Kurs** automatisch ergänzt.
        - Die Spalte **Person** bietet ein Dropdown mit den Kürzeln (JL, DD, JP, JI, KK, MO).
        - **Kategorie** und **Bemerkung** sind Freitextfelder für eigene Notizen.

        #### 2. Preis-Levels & Validierung
        Du kannst Stop Loss, Einstiegs- und Take-Profit-Levels definieren. Beim Speichern werden folgende Bedingungen geprüft:
        - **Stop Loss:** Muss kleiner als **Einstieg 1** sein.
        - **Einstieg 1-3:** Level für Käufe. Es muss gelten: `Einstieg 1 < Einstieg 2 < Einstieg 3`.
        - **Take Profit 1-3:** Level für Verkäufe. Es muss gelten: `Einstieg 1 < Take Profit 1` und `TP1 < TP2 < TP3`.
        - Alle Werte müssen positive Zahlen sein.

        #### 3. Automatische Formatierung (Farben)
        Die obere Tabelle (**Aktuelle Watchlist**) zeigt farbliche Hervorhebungen basierend auf dem aktuellen Marktkurs:
        - 🔴 **Rot:** Der aktuelle Kurs hat den **Stop Loss** unterschritten (`Kurs < Stop Loss`).
        - 🔵 **Blau:** Der aktuelle Kurs hat ein **Einstiegs-Level** erreicht oder unterschritten (`Kurs <= Einstieg`). Je tiefer der Kurs (E3 vs. E1), desto dunkler das Blau.
        - 🟢 **Grün:** Der aktuelle Kurs hat ein **Take-Profit-Level** erreicht oder überschritten (`Kurs >= Take Profit`). Je höher der Kurs (TP3 vs. TP1), desto dunkler das Grün.

        #### 4. Speichern & Backup
        - Änderungen im Editor werden erst gespeichert, wenn du auf **'Änderungen speichern'** klickst.
        - Bei jedem Speichervorgang wird automatisch ein **Backup** im Ordner `data/backups` erstellt.
        - Backups können über die Sektion **'Backup & Restore'** wiederhergestellt werden.

        #### 5. Claude KI Analyse & Berichte
        - Wähle ein Symbol im Bereich **'Claude KI Analyse & Berichte'** aus.
        - **KI-Analyse:** Klicke auf **'Analyse in Claude öffnen'**, um einen Deep-Link zu Claude.ai mit einem **sektorspezifischen Prompt** zu generieren.
        - **Berichte:** Du kannst HTML-Exporte von KI-Analysen hochladen, um sie dauerhaft dem Symbol zuzuordnen und direkt in der App anzuzeigen.
        """)

if __name__ == "__main__":
    main()
