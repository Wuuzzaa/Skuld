import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError

def download_csv_from_drive(service_account_file, file_id):
    """
    Downloads a file from Google Drive using a service account.
    If the file is a Google Spreadsheet, it is exported as CSV.
    
    Note: The service_account_file should be the local path where the service account JSON file
    has been generated from your GitHub secret (e.g., "service_account.json").

    :param service_account_file: Path to the locally saved service account JSON file.
    :param file_id: ID of the file on Google Drive.
    :return: A BytesIO stream containing the file data, or None if an error occurs.
    """
    try:
        # Load credentials from the service account JSON file.
        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        # Build the Drive API client.
        service = build("drive", "v3", credentials=creds)
        
        # Retrieve file metadata to determine its MIME type.
        file_info = service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
        mime_type = file_info.get("mimeType", "")
        
        # Choose the correct download request based on file type.
        if mime_type == "application/vnd.google-apps.spreadsheet":
            # Export a Google Spreadsheet as CSV.
            request = service.files().export_media(fileId=file_id, mimeType="text/csv")
        else:
            # Download a regular file (e.g., a CSV file).
            request = service.files().get_media(fileId=file_id)
        
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"Download Progress: {int(status.progress() * 100)}%")
        
        # Reset the stream's position to the beginning.
        file_stream.seek(0)
        return file_stream

    except HttpError as error:
        print(f"An error occurred: {error}")
        return None
