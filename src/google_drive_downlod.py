import os
import io
import json
import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo  # Für Python 3.9+; bei älteren Versionen: backports.zoneinfo
from src.custom_logging import log_info, log_error, log_write

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# ----------------------
# Konfiguration
# ----------------------
PATH_DATAFRAME_DATA_MERGED_CSV = "data/merged_data.csv"  # Lokaler Speicherort der CSV
FILE_NAME = "merged_data.csv"                              # Dateiname, wie er auf Google Drive vorliegt
PARENT_FOLDER_ID = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"     # ID des Google Drive-Ordners
LOCAL_TZ = "Europe/Berlin"                                 # Lokale Zeitzone (CET)
UPDATE_TIMES = [time(10, 15), time(16, 15)]                # Update-Zeiten in lokaler Zeitzone

# ----------------------
# Google Drive Funktionen
# ----------------------
def get_credentials():
    """
    Liest die Service Account-Credentials aus den Streamlit-Secrets (im Abschnitt [service_account])
    und erstellt ein Credentials-Objekt.
    """
    # Wir gehen davon aus, dass in deiner .streamlit/secrets.toml der Abschnitt [service_account] vorhanden ist
    service_account_dict = st.secrets["service_account"]
    return service_account.Credentials.from_service_account_info(
        service_account_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

def find_file_id_by_name(file_name, parent_folder_id=None):
    """
    Sucht auf Google Drive nach einer Datei mit dem angegebenen Namen und gibt deren ID zurück.
    Optional kann der Ordner (parent_folder_id) eingeschränkt werden.
    """
    try:
        creds = get_credentials()
        service = build("drive", "v3", credentials=creds)

        query = f"name = '{file_name}' and trashed = false"
        if parent_folder_id:
            query += f" and '{parent_folder_id}' in parents"

        results = service.files().list(
            q=query,
            spaces="drive",
            fields="files(id, name)",
            pageSize=1
        ).execute()

        files = results.get("files", [])
        if not files:
            log_error("Keine Datei mit diesem Namen gefunden.")
            return None
        else:
            file = files[0]
            log_info(f"Gefundene Datei: {file.get('name')} (ID: {file.get('id')})")
            return file.get("id")
    except HttpError as error:
        log_error(f"Ein Fehler ist aufgetreten: {error}")
        return None


def download_csv_from_drive(file_id):
    """
    Lädt die Datei (CSV oder als exportiertes Google Spreadsheet) von Google Drive herunter.
    Gibt einen BytesIO-Stream zurück.
    """
    try:
        creds = get_credentials()
        service = build("drive", "v3", credentials=creds)

        # modifiedTime zusätzlich anfordern
        file_info = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, modifiedTime"
        ).execute()

        mime_type = file_info.get("mimeType", "")

        # modifiedTime aus den Metadaten in ein lokales Datum umwandeln und anzeigen
        modified_time_str = file_info.get("modifiedTime")
        if modified_time_str:
            modified_time_utc = datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
            modified_time_local = modified_time_utc.astimezone(ZoneInfo(LOCAL_TZ))
            log_info(f"Datei zuletzt geändert (Google Drive): {modified_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        # CSV herunterladen
        if mime_type == "application/vnd.google-apps.spreadsheet":
            request = service.files().export_media(fileId=file_id, mimeType="text/csv")
        else:
            request = service.files().get_media(fileId=file_id)

        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                log_write(f"Download-Fortschritt: {int(status.progress() * 100)}%")

        file_stream.seek(0)
        return file_stream

    except HttpError as error:
        log_error(f"Ein Fehler ist aufgetreten: {error}")
        return None



# ----------------------
# Update-Logik (Zeitprüfung)
# ----------------------
def get_update_datetime(local_update_time: time, tz_name=LOCAL_TZ) -> datetime:
    """
    Erzeugt ein timezone-bewusstes Datum für die gegebene Update-Zeit (z. B. 10:15 oder 16:15) in der lokalen Zeitzone
    und wandelt es in UTC um.
    """
    today_local = datetime.now(ZoneInfo(tz_name)).date()
    local_dt = datetime.combine(today_local, local_update_time, tzinfo=ZoneInfo(tz_name))
    return local_dt.astimezone(ZoneInfo("UTC"))

def file_last_modified(path) -> datetime:
    """
    Gibt den letzten Änderungszeitpunkt der Datei als timezone-bewusstes UTC-datetime zurück.
    """
    return datetime.fromtimestamp(os.path.getmtime(path), tz=ZoneInfo("UTC"))

def should_update_file(local_file, update_times, tz_name=LOCAL_TZ) -> bool:
    """
    Prüft, ob die lokale Datei aktualisiert werden soll.
    Logik:
      - Falls die Datei nicht existiert, muss sie aktualisiert werden.
      - An Werktagen (Mo-Fr) wird geprüft, ob für eine der definierten Update-Zeiten (in CET) bereits
        erreicht wurde und ob die Datei vor dieser Zeit zuletzt modifiziert wurde.
    """
    if not os.path.exists(local_file):
        return True

    last_mod = file_last_modified(local_file)
    now = datetime.now(ZoneInfo("UTC"))
    if now.weekday() < 6:  # Montag bis Freitag
        for ut in update_times:
            update_dt_utc = get_update_datetime(ut, tz_name)
            if now >= update_dt_utc and last_mod < update_dt_utc:
                return True
    return False

@st.cache_data(ttl=1800, show_spinner="Lade aktualisierte Daten...")
def load_updated_data():
    """
    Lädt die CSV-Daten. Wird die lokale Datei als veraltet erkannt, so wird sie von Google Drive heruntergeladen,
    lokal gespeichert und als DataFrame eingelesen. Andernfalls wird die lokale Datei verwendet.
    Der Cache ist auf 1800 Sekunden (30 min) gesetzt.
    """
    if should_update_file(PATH_DATAFRAME_DATA_MERGED_CSV, UPDATE_TIMES):
        log_info("Neue Datei verfügbar – starte Download von Google Drive ...")
        file_id = find_file_id_by_name(FILE_NAME, PARENT_FOLDER_ID)
        if file_id is None:
            log_error("Datei mit dem angegebenen Namen wurde auf Google Drive nicht gefunden.")
            return None

        file_stream = download_csv_from_drive(file_id)
        if file_stream is None:
            return None

        # Sicherstellen, dass der Zielordner existiert
        os.makedirs(os.path.dirname(PATH_DATAFRAME_DATA_MERGED_CSV), exist_ok=True)

        # Falls die lokale Datei bereits existiert, löschen wir sie zuerst
        if os.path.exists(PATH_DATAFRAME_DATA_MERGED_CSV):
            os.remove(PATH_DATAFRAME_DATA_MERGED_CSV)

        with open(PATH_DATAFRAME_DATA_MERGED_CSV, "wb") as f:
            f.write(file_stream.read())

        file_stream.seek(0)
        try:
            df = pd.read_csv(file_stream)
            log_info("Neue CSV-Datei erfolgreich heruntergeladen und eingelesen.")
            return df
        except Exception as e:
            log_error(f"Fehler beim Lesen der CSV: {e}")
            return None
    else:
        log_info("Lade lokale Datei ...")
        try:
            df = pd.read_csv(PATH_DATAFRAME_DATA_MERGED_CSV)
            last_mod = file_last_modified(PATH_DATAFRAME_DATA_MERGED_CSV)
            last_mod_local = last_mod.astimezone(ZoneInfo(LOCAL_TZ))
            log_info(f"Lokale Datei zuletzt geändert am: {last_mod_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return df
        except Exception as e:
            log_error(f"Fehler beim Lesen der CSV: {e}")
            return None

