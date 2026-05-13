import pandas as pd
import os
import streamlit as st
import datetime
from src.database import select_into_dataframe_pg

# Konfiguration
WATCHLIST_FILE = "data/watchlist.xlsx"
PERSONS = ["JL", "DD", "JP", "JI", "KK", "MO"]
COLUMNS = [
    "Symbol", "Unternehmen", "timestamp", "Person", "Bemerkung",
    "Level Kaufkurs 1", "Level Kaufkurs 2", "Level Kaufkurs 3",
    "Level Verkaufkurs 1", "Level Verkaufkurs 2", "Level Verkaufkurs 3",
    "Aktueller Kurs"
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
        df_symbols = select_into_dataframe_pg('select distinct symbol from "OptionDataMerged" ORDER BY symbol ASC')
        if df_symbols is not None and not df_symbols.empty:
            return df_symbols['symbol'].tolist()
    except Exception as e:
        st.warning(f"Konnte Symbole nicht aus DB laden: {e}")
    return []

def main():
    st.title("Watchlist")

    # Daten laden
    if 'watchlist_df' not in st.session_state:
        st.session_state.watchlist_df = load_watchlist()
    
    valid_symbols = get_valid_symbols()

    # Editor Setup
    column_config = {
        "Symbol": st.column_config.SelectboxColumn("Symbol", help="Aktien Ticker", required=True, options=valid_symbols),
        "Person": st.column_config.SelectboxColumn("Person", options=PERSONS),
        "timestamp": st.column_config.DatetimeColumn("Zeitstempel", disabled=True),
        "Aktueller Kurs": st.column_config.NumberColumn("Aktueller Kurs", disabled=True),
        "Level Kaufkurs 1": st.column_config.NumberColumn("Kauf 1", format="%.2f"),
        "Level Kaufkurs 2": st.column_config.NumberColumn("Kauf 2", format="%.2f"),
        "Level Kaufkurs 3": st.column_config.NumberColumn("Kauf 3", format="%.2f"),
        "Level Verkaufkurs 1": st.column_config.NumberColumn("Verkauf 1", format="%.2f"),
        "Level Verkaufkurs 2": st.column_config.NumberColumn("Verkauf 2", format="%.2f"),
        "Level Verkaufkurs 3": st.column_config.NumberColumn("Verkauf 3", format="%.2f"),
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
                        # Wir markieren das Symbol oder den aktuellen Kurs? 
                        # Vorgabe: "die anzeige soll abhänig von der realtion... unterschiedlich formatiert werden"
                        # Wir färben die ganze Zeile oder spezifische Zellen.
                        # Hier färben wir die Hintergrundfarbe der Zeile.
                        return ['background-color: #d4edda'] * len(row) # Hellgrün

                # Verkaufslevel (Rot wenn Kurs >= Level)
                for i in range(1, 4):
                    col_name = f'Level Verkaufkurs {i}'
                    if not pd.isna(row[col_name]) and current_price >= row[col_name]:
                        return ['background-color: #f8d7da'] * len(row) # Hellrot
            except:
                pass
            return styles

        return df.style.apply(color_levels, axis=1)

    st.subheader("Aktuelle Watchlist")
    st.dataframe(style_watchlist(st.session_state.watchlist_df), width="stretch")

    st.subheader("Bearbeitungsmodus")
    edited_df = st.data_editor(
        st.session_state.watchlist_df,
        column_config=column_config,
        num_rows="dynamic",
        width="stretch",
        key="watchlist_editor"
    )

    # Logik für Änderungen (Timestamp & Validierung)
    if st.button("Änderungen speichern"):
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
        # Da st.data_editor direkt das ganze DF zurückgibt, setzen wir den Timestamp für alles was sich "potenziell" geändert hat
        # Einfachheitshalber setzen wir ihn jetzt für alle Zeilen, die im Editor vorhanden sind, 
        # oder wir vergleichen zeilenweise.
        
        now = datetime.datetime.now().replace(microsecond=0)
        
        # Um nur geänderte Zeilen zu markieren, müssten wir den State tracken.
        # Streamlit's data_editor gibt uns im State 'watchlist_editor' die 'edited_rows', 'added_rows', 'deleted_rows'.
        
        changes = st.session_state.watchlist_editor
        has_changes = False
        
        if changes['edited_rows'] or changes['added_rows'] or changes['deleted_rows']:
            has_changes = True
            
            # Neue Zeilen bekommen Timestamp
            for row_idx in changes['edited_rows']:
                edited_df.iloc[row_idx, edited_df.columns.get_loc('timestamp')] = now
            
            # Bei added_rows müssen wir aufpassen, da sie oft am Ende stehen
            # Aber edited_df enthält sie bereits. Wir müssen herausfinden welche das sind.
            # Ein einfacherer Weg: Wenn die Zeile in 'added_rows' ist.
            # Da added_rows eine Liste von dicts ist, ist es schwerer die Indexe in edited_df zu finden.
            
            # Pragmatischer Ansatz: Wenn sich was geändert hat, speichern wir.
            # Wir setzen den Timestamp für alle geänderten/neuen Zeilen.
            for row in changes['added_rows']:
                # Finde die neue Zeile im edited_df (meistens die letzten)
                # Da st.data_editor die neuen Zeilen ans Ende hängt:
                pass # Siehe unten

        # Robusterer Ansatz für Timestamps in st.data_editor:
        # Wir vergleichen das ursprüngliche DF mit dem neuen.
        for idx in edited_df.index:
            if idx >= len(st.session_state.watchlist_df):
                # Neue Zeile
                edited_df.loc[idx, 'timestamp'] = now
            else:
                # Bestehende Zeile - vergleiche Inhalt (ohne timestamp)
                original_row = st.session_state.watchlist_df.iloc[idx].drop('timestamp')
                new_row = edited_df.loc[idx].drop('timestamp')
                if not original_row.equals(new_row):
                    edited_df.loc[idx, 'timestamp'] = now

        st.session_state.watchlist_df = edited_df
        save_watchlist(edited_df)

if __name__ == "__main__":
    main()
