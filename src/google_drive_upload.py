import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

def upload_csv_to_drive(service_account_file, file_path, file_name, parent_folder_id, convert_to_google_format=False):
    """
    Lädt eine CSV-Datei per Service Account zu Google Drive hoch.
    Prüft, ob im Zielordner bereits eine Datei mit dem gleichen Namen existiert. Falls ja, wird diese gelöscht.
    Optional kann die Datei in ein Google-Format konvertiert werden (z.B. Google Sheets).

    :param service_account_file: Pfad zur Service-Account-JSON-Datei
    :param file_path: Lokaler Pfad zur hochzuladenden CSV
    :param file_name: Name der Datei auf Google Drive
    :param parent_folder_id: ID des Zielordners auf Google Drive
    :param convert_to_google_format: True, wenn als Google Spreadsheet konvertiert werden soll
    :return: ID der hochgeladenen Datei oder None bei Fehler
    """
    try:
        # Service Account Credentials laden
        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/drive"]
        )

        # Drive API-Client erstellen
        service = build("drive", "v3", credentials=creds)

        # Prüfen, ob im Zielordner bereits eine Datei mit file_name existiert
        query = f"name = '{file_name}' and '{parent_folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get('files', [])
        if files:
            for file in files:
                print(f"Datei '{file['name']}' mit ID {file['id']} existiert bereits. Lösche diese...")
                service.files().delete(fileId=file['id']).execute()
                print("Datei gelöscht.")

        # Metadaten für die neue Datei
        file_metadata = {
            "name": file_name,              # Dateiname in Google Drive
            "parents": [parent_folder_id]   # Zielordner
        }

        # Optional: Konvertierung in Google Spreadsheet
        if convert_to_google_format:
            file_metadata["mimeType"] = "application/vnd.google-apps.spreadsheet"

        media = MediaFileUpload(file_path, mimetype="text/csv", chunksize=256*1024, resumable=True)
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload-Fortschritt: {int(status.progress() * 100)}%")

        file_id = response.get("id")
        print(f"Datei mit der ID: '{file_id}' wurde hochgeladen.")
        return file_id

    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return None
