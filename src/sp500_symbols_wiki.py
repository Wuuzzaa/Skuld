from io import StringIO
import logging
import os
import sys
import pandas as pd
import requests


# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table
from config import TABLE_STOCK_SP500_CONSTITUENTS_HISTORICAL

logger = logging.getLogger(os.path.basename(__file__))

url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def load_sp500_constituents_from_wikipedia():
    """
    Load S&P 500 constituents from Wikipedia and reconstruct historical data.
    """

    # 1. Daten holen
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    # StringIO löst die Pandas-FutureWarning auf
    tables = pd.read_html(StringIO(response.text))

    df_current = tables[0]
    df_changes = tables[1]

    print(len(df_current), len(df_changes))
    # --- 2. Vorbereitung der Änderungstabelle ---
    # Wikipedia nutzt Multi-Index Spalten bei den Änderungen. Wir flachklopfen diese.
    df_changes.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in df_changes.columns]

    # Spaltennamen normalisieren (beugt Fehlern vor, falls sich bei Wikipedia Spalten-Benennungen ändern)
    rename_dict = {}
    for col in df_changes.columns:
        if 'Date' in col: rename_dict[col] = 'date'
        elif 'Added_Ticker' in col or ('Added' in col and 'Ticker' in col): rename_dict[col] = 'added_ticker'
        elif 'Removed_Ticker' in col or ('Removed' in col and 'Ticker' in col): rename_dict[col] = 'removed_ticker'

    df_changes = df_changes.rename(columns=rename_dict)[['date', 'added_ticker', 'removed_ticker']]
    df_changes = df_changes[df_changes.added_ticker != df_changes.removed_ticker]  # Filter out rows where both added and removed are NaN

    # Datum in echtes datetime-Objekt umwandeln
    df_changes['date'] = pd.to_datetime(df_changes['date'], errors='coerce')
    # Sortieren von neu nach alt (chronologisch rückwärts)
    df_changes = df_changes.sort_values(by='date', ascending=False).dropna(subset=['date'])


    # --- 3. Rekonstruktion des historischen Verlaufs (Robustere Version) ---
    history_records = []

    # Wir tracken den aktuellen Zustand jedes Tickers.
    # Key: Ticker, Value: Das offene 'date_removed'
    active_tickers = {symbol: None for symbol in df_current['Symbol'].unique()}

    # Iteration rückwärts durch die Geschichte
    for _, row in df_changes.iterrows():
        change_date = row['date'].date()
        added = row['added_ticker'] if pd.notna(row['added_ticker']) else None
        removed = row['removed_ticker'] if pd.notna(row['removed_ticker']) else None
        
        # KORREKTUR FALL A: Ein Symbol wird entfernt
        if removed:
            if removed in active_tickers:
                # Wenn es schon aktiv ist (z.B. weil es heute im Index ist), 
                # bedeutet das, es war von diesem Änderungsdatum bis zum bekannten Austritt (oder None) im Index.
                rem_date = active_tickers[removed]
                history_records.append({
                    'symbol': removed,
                    'date_added': change_date, # Es war mindestens seit diesem Tag (wieder) drin
                    'date_removed': rem_date
                })
                # Jetzt setzen wir das Tracking zurück auf dieses Datum für die Zeit davor
                active_tickers[removed] = change_date
            else:
                # Wenn wir das Symbol noch nicht kennen, eröffnen wir einen neuen Zeitraum
                active_tickers[removed] = change_date
            
        # FALL B: Ein Symbol wird hinzugefügt
        if added:
            if added in active_tickers:
                rem_date = active_tickers[added]
                history_records.append({
                    'symbol': added,
                    'date_added': change_date,
                    'date_removed': rem_date
                })
                # Da es hier hinzugefügt wurde, war es vor diesem Datum (rückwärts betrachtet) nicht im Index
                del active_tickers[added]
            else:
                # Sonderfall: Ein "Added"-Event ohne vorheriges Tracking (Datenungenauigkeit bei Wikipedia)
                history_records.append({
                    'symbol': added,
                    'date_added': change_date,
                    'date_removed': change_date # Nur ein temporärer Punkt-Eintrag
                })

    # Für alle Ticker, die jetzt noch übrig sind (Urgesteine)
    for symbol, rem_date in active_tickers.items():
        history_records.append({
            'symbol': symbol,
            'date_added': None,
            'date_removed': rem_date
        })

    # --- 3.1 Nachbereitung & Bereinigung von Überlappungen ---
    df_history = pd.DataFrame(history_records)

    # Duplikate filtern, falls exakt gleiche Zeiträume entstanden sind
    df_history = df_history.drop_duplicates(subset=['symbol', 'date_added', 'date_removed'])

    # Wichtig: Falls Einträge existieren, bei denen date_added == date_removed (durch Bereinigungen), 
    # und es gibt für dasselbe Symbol einen offeneren Zeitraum, entfernen wir die fehlerhaften Punkt-Einträge
    df_history = df_history[~((df_history['date_added'] == df_history['date_removed']) & (df_history['date_added'].notna()))]

    # --- 4. Finaler DataFrame ---
    df_history = pd.DataFrame(history_records)

    # Sortieren für bessere Lesbarkeit
    df_history = df_history.sort_values(by=['symbol', 'date_added'], ascending=[True, True]).reset_index(drop=True)

    # Spaltenreihenfolge erzwingen
    df_history = df_history[['symbol', 'date_added', 'date_removed']]

    # --- Database Persistence ---
    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_STOCK_SP500_CONSTITUENTS_HISTORICAL)
        insert_into_table(
            connection,
            table_name=f"{TABLE_STOCK_SP500_CONSTITUENTS_HISTORICAL}",
            dataframe=df_history,
            if_exists="append"
        )

    # with get_postgres_engine().begin() as connection:
    #     truncate_table(connection, "StockSP500ConstituentsCurrent")
    #     insert_into_table(
    #         connection,
    #         table_name=f"StockSP500ConstituentsCurrent",
    #         dataframe=df_current,
    #         if_exists="append"
    #     )

    # with get_postgres_engine().begin() as connection:
    #     truncate_table(connection, "StockSP500ConstituentsChanges")
    #     insert_into_table(
    #         connection,
    #         table_name=f"StockSP500ConstituentsChanges",
    #         dataframe=df_changes,
    #         if_exists="append"
    #     )
    logger.info(f"Saved S&P 500 constituents data to database - rows: {len(df_history)}")

    # print("\n--- REKONSTRUIERTER DATAFRAME (Auszug) ---")
    # print(df_history.to_string(max_rows=30))

def get_sp500_symbols_for_date(target_date):
    """
    Holt alle S&P 500 Symbole, die an einem bestimmten Datum aktiv im Index waren.
    """
    
    query = """
        SELECT DISTINCT symbol 
        FROM "StockSP500ConstituentsHistorical"
        WHERE (date_added <= :target_date OR date_added IS NULL)
          AND (date_removed > :target_date OR date_removed IS NULL)
    """
    
    df_symbols = select_into_dataframe(query, params={"target_date": target_date})
    
    if df_symbols.empty:
        return []
        
    return df_symbols['symbol'].tolist()