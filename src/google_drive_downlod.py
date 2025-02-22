import os
import io
import streamlit as st
import pandas as pd

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

# Konfiguration: Passe diese Werte an deine Umgebung an.
PATH_DATAFRAME_DATA_MERGED_CSV = "data/merged_data.csv"  # Lokaler Speicherort der CSV
SERVICE_ACCOUNT_FILE = "service_account.json"            # Pfad zur Service-Account-JSON-Datei
FILE_NAME = "merged_data.csv"                              # Dateiname, nach dem gesucht werden soll
PARENT_FOLDER_ID = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"                       # ID des Ordners, in dem gesucht werden soll (oder None, wenn nicht benötigt)

def find_file_id_by_name(service_account_file, file_name, parent_folder_id=None):
    """
    Sucht auf Google Drive nach einer Datei mit dem angegebenen Namen und gibt die Datei-ID zurück.
    Optional kann eine parent_folder_id angegeben werden, um die Suche auf einen bestimmten Ordner zu beschränken.
    
    :param service_account_file: Pfad zur Service-Account-JSON-Datei.
    :param file_name: Der Name der Datei, nach der gesucht werden soll.
    :param parent_folder_id: (Optional) ID des Ordners, in dem gesucht werden soll.
    :return: Die Datei-ID, falls gefunden, sonst None.
    """
    try:
        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds)
        
        # Baue die Suchquery, inkl. Ordner-ID, falls angegeben
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
            print("Keine Datei mit diesem Namen gefunden.")
            return None
        else:
            file = files[0]
            print(f"Gefundene Datei: {file.get('name')} (ID: {file.get('id')})")
            return file.get("id")
    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None

def download_csv_from_drive(service_account_file, file_id):
    """
    Lädt eine Datei von Google Drive über einen Service-Account herunter.
    Falls es sich um ein Google Spreadsheet handelt, wird es als CSV exportiert.
    
    :param service_account_file: Pfad zur Service-Account-JSON-Datei.
    :param file_id: ID der Datei in Google Drive.
    :return: Ein BytesIO-Stream mit dem Dateiinhalt oder None bei Fehler.
    """
    try:
        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        service = build("drive", "v3", credentials=creds)
        
        # Hole Dateiinformationen (z. B. MIME-Typ)
        file_info = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
        mime_type = file_info.get("mimeType", "")
        
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
                print(f"Download-Fortschritt: {int(status.progress() * 100)}%")
        
        file_stream.seek(0)
        return file_stream

    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None

def load_data():
    """
    Lädt die CSV-Datei. Falls sie lokal nicht existiert, wird sie von Google Drive heruntergeladen.
    Gibt einen DataFrame zurück oder None, wenn etwas schiefgeht.
    """
    if not os.path.exists(PATH_DATAFRAME_DATA_MERGED_CSV):
        st.info("Lokale Datei nicht gefunden. Suche Datei-ID anhand des Dateinamens ...")
        file_id = find_file_id_by_name(SERVICE_ACCOUNT_FILE, FILE_NAME, PARENT_FOLDER_ID)
        if file_id is None:
            st.error("Datei mit dem angegebenen Namen wurde auf Google Drive nicht gefunden.")
            return None
        st.info("Datei-ID gefunden. Starte Download von Google Drive ...")
        file_stream = download_csv_from_drive(SERVICE_ACCOUNT_FILE, file_id)
        if file_stream is None:
            return None
        
        # Speichere die heruntergeladene Datei lokal, damit sie beim nächsten Mal direkt geladen werden kann.
        with open(PATH_DATAFRAME_DATA_MERGED_CSV, "wb") as f:
            f.write(file_stream.read())
        
        # Zurücksetzen des Streams, damit er erneut gelesen werden kann
        file_stream.seek(0)
        try:
            df = pd.read_csv(file_stream)
            return df
        except Exception as e:
            print(f"Fehler beim Lesen der CSV: {e}")
            return None
    else:
        try:
            df = pd.read_csv(PATH_DATAFRAME_DATA_MERGED_CSV)
            return df
        except Exception as e:
            print(f"Fehler beim Lesen der CSV: {e}")
            return None


