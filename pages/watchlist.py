import pandas as pd
import os
import streamlit as st
import datetime
from src.database import select_into_dataframe_pg

# Konfiguration
WATCHLIST_FILE = "data/watchlist.xlsx"
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
    try:
        df.to_excel(WATCHLIST_FILE, index=False)
        st.success("Watchlist erfolgreich gespeichert!")
    except Exception as e:
        st.error(f"Fehler beim Speichern der Watchlist: {e}")

@st.cache_data
def get_valid_symbols():
    try:
        # Versuche Symbole aus der Datenbank zu laden
        df_symbols = select_into_dataframe_pg('select distinct symbol, live_stock_price, company_name from "OptionDataMerged" ORDER BY symbol ASC')
        if df_symbols is not None and not df_symbols.empty:
            return df_symbols
    except Exception as e:
        st.warning(f"Konnte Symbole nicht aus DB laden: {e}")
    return pd.DataFrame(columns=['symbol', 'live_stock_price', 'company_name'])

def main():
    st.title("Watchlist")

    # Daten laden
    if 'watchlist_df' not in st.session_state:
        st.session_state.watchlist_df = load_watchlist()
    
    df_symbols = get_valid_symbols()
    valid_symbols = df_symbols['symbol'].tolist() if not df_symbols.empty else []

    # Editor Setup
    column_config = {
        "Symbol": st.column_config.SelectboxColumn("Symbol", help="Aktien Ticker", required=True, options=valid_symbols),
        "Unternehmen": st.column_config.TextColumn("Unternehmen", disabled=True),
        "Person": st.column_config.SelectboxColumn("Person", options=PERSONS),
        "timestamp": st.column_config.DatetimeColumn("Zeitstempel", disabled=True),
        "Aktueller Kurs": st.column_config.NumberColumn("Aktueller Kurs", format="%.2f $", disabled=True),
        "Level Kaufkurs 1": st.column_config.NumberColumn("Kauf 1", format="%.2f $", min_value=0.0),
        "Level Kaufkurs 2": st.column_config.NumberColumn("Kauf 2", format="%.2f $", min_value=0.0),
        "Level Kaufkurs 3": st.column_config.NumberColumn("Kauf 3", format="%.2f $", min_value=0.0),
        "Level Verkaufkurs 1": st.column_config.NumberColumn("Verkauf 1", format="%.2f $", min_value=0.0),
        "Level Verkaufkurs 2": st.column_config.NumberColumn("Verkauf 2", format="%.2f $", min_value=0.0),
        "Level Verkaufkurs 3": st.column_config.NumberColumn("Verkauf 3", format="%.2f $", min_value=0.0),
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
                
                # Kauflevel (Grün wenn Kurs <= Level)
                for i in range(1, 4):
                    col_name = f'Level Kaufkurs {i}'
                    if not pd.isna(row[col_name]) and current_price <= row[col_name]:
                        return ['background-color: #d4edda'] * len(row) # Hellgrün

                # Verkaufslevel (Rot wenn Kurs >= Level)
                for i in range(1, 4):
                    col_name = f'Level Verkaufkurs {i}'
                    if not pd.isna(row[col_name]) and current_price >= row[col_name]:
                        return ['background-color: #f8d7da'] * len(row) # Hellrot
            except:
                pass
            return styles

        # Währungsspalten definieren
        currency_cols = ["Aktueller Kurs", "Level Kaufkurs 1", "Level Kaufkurs 2", "Level Kaufkurs 3", 
                         "Level Verkaufkurs 1", "Level Verkaufkurs 2", "Level Verkaufkurs 3"]
        
        return df.style.apply(color_levels, axis=1).format({col: "{:.2f} $" for col in currency_cols}, na_rep="-")

    st.subheader("Aktuelle Watchlist")
    st.dataframe(style_watchlist(st.session_state.watchlist_df), width="stretch")

    st.subheader("Bearbeitungsmodus")
    
    # Automatischer Abgleich bei Symbolwahl (vor dem Rendern des Editors)
    if "watchlist_editor" in st.session_state and not df_symbols.empty:
        changes = st.session_state.watchlist_editor
        symbol_map = df_symbols.set_index('symbol')
        any_auto_update = False
        
        # Geänderte Zeilen prüfen
        for row_idx_str, edited_cols in changes.get('edited_rows', {}).items():
            if 'Symbol' in edited_cols:
                new_symbol = edited_cols['Symbol']
                if new_symbol in symbol_map.index:
                    row_idx = int(row_idx_str)
                    # Wir holen die Zeile aus dem aktuellen DF
                    db_row = symbol_map.loc[new_symbol]
                    
                    # Wenn es sich um eine neu hinzugefügte Zeile handelt, die bereits im DF ist
                    if row_idx < len(st.session_state.watchlist_df):
                        st.session_state.watchlist_df.at[row_idx, 'Symbol'] = new_symbol
                        st.session_state.watchlist_df.at[row_idx, 'Unternehmen'] = db_row['company_name']
                        st.session_state.watchlist_df.at[row_idx, 'Aktueller Kurs'] = db_row['live_stock_price']
                        # Den Editor State bereinigen für diese Spalte, damit kein Loop entsteht
                        # aber wir machen eh ein rerun.
                        any_auto_update = True
        
        # Neue Zeilen prüfen (added_rows)
        # added_rows sind noch nicht im watchlist_df. 
        # Wenn wir sie hier direkt ins watchlist_df einfügen, wird st.data_editor sie als existierende Zeilen anzeigen.
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
            
            # Wichtig: Wenn wir added_rows manuell übernommen haben, müssen wir den editor state leeren
            # oder zumindest wissen, dass wir sie verarbeitet haben.
            if any_auto_update:
                # Wir löschen die verarbeiteten added_rows aus dem Editor state
                st.session_state.watchlist_editor['added_rows'] = []

        if any_auto_update:
            st.rerun()

    edited_df = st.data_editor(
        st.session_state.watchlist_df,
        column_config=column_config,
        num_rows="dynamic",
        width="stretch",
        key="watchlist_editor"
    )

    # Logik für Änderungen (Timestamp & Validierung)
    if st.button("Änderungen speichern"):
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
        
        # Duplikate checken
        if edited_df['Symbol'].duplicated().any():
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
        for idx in edited_df.index:
            if idx >= len(st.session_state.watchlist_df):
                # Neue Zeile
                edited_df.loc[idx, 'timestamp'] = now
            else:
                # Bestehende Zeile - vergleiche Inhalt (ohne timestamp)
                # Wir konvertieren zu Strings für den Vergleich, um Typ-Probleme zu vermeiden
                original_row = st.session_state.watchlist_df.iloc[idx].drop('timestamp').fillna('').astype(str)
                new_row = edited_df.loc[idx].drop('timestamp').fillna('').astype(str)
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
        save_watchlist(edited_df)
        st.rerun()

if __name__ == "__main__":
    main()
