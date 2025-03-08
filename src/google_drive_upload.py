import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from config import PATH_DATAFRAME_DATA_MERGED_FEATHER , FILENAME_GOOGLE_DRIVE, PATH_ON_GOOGLE_DRIVE, PATH_FOR_SERVICE_ACCOUNT_FILE  
from src.custom_logging import log_info, log_error, log_write, show_log_messages


def upload_feather_to_drive(service_account_file, file_path, file_name, parent_folder_id, convert_to_google_format=False):
    """
    Uploads a Feather file to Google Drive using a Service Account.
    Checks if a file with the same name already exists in the target folder. If so, it deletes that file.
    Optionally, the file can be converted to a Google format (e.g., Google Sheets), though for a Feather file
    conversion is typically not applicable.

    :param service_account_file: Path to the Service Account JSON file
    :param file_path: Local path to the Feather file to be uploaded
    :param file_name: Name of the file on Google Drive
    :param parent_folder_id: ID of the target folder on Google Drive
    :param convert_to_google_format: True if the file should be converted to a Google Spreadsheet (not usually used for Feather files)
    :return: ID of the uploaded file or None in case of an error
    """
    try:
        # Load Service Account credentials
        creds = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=["https://www.googleapis.com/auth/drive"]
        )

        # Create the Drive API client
        service = build("drive", "v3", credentials=creds)

        # Check if a file with file_name already exists in the target folder
        query = f"name = '{file_name}' and '{parent_folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])

        if files:
            for file in files:
                log_info(f"File '{file['name']}' with ID {file['id']} already exists. Deleting it...")
                service.files().delete(fileId=file["id"]).execute()
                log_info("File deleted.")

        # Metadata for the new file
        file_metadata = {
            "name": file_name,
            "parents": [parent_folder_id]
        }

        # Optionally: Convert to Google Spreadsheet format (not common for Feather files)
        if convert_to_google_format:
            file_metadata["mimeType"] = "application/vnd.google-apps.spreadsheet"

        # Upload the file; using application/octet-stream as the mimetype for a Feather file
        media = MediaFileUpload(file_path, mimetype="application/octet-stream", chunksize=256*1024, resumable=True)
        request = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                log_info(f"Upload progress: {int(status.progress() * 100)}%")

        file_id = response.get("id")
        log_info(f"File with ID: '{file_id}' has been uploaded.")
        return file_id

    except HttpError as error:
        log_error(f"An error occurred: {error}")
        return None


def upload_merged_data():
    """
    Executes the upload of the merged Feather file to Google Drive.
    This function encapsulates the upload step and internally calls upload_feather_to_drive.
    """
    # Beispiel-Pfade/Variablen: Ersetze sie durch deine Konstanten oder Variablen
    service_account_file = PATH_FOR_SERVICE_ACCOUNT_FILE  # Path to the Service Account JSON file
    parent_folder_id = PATH_ON_GOOGLE_DRIVE  # Target folder ID in Google Drive
    file_path = PATH_DATAFRAME_DATA_MERGED_FEATHER  # Local path to the merged Feather file
    file_name = FILENAME_GOOGLE_DRIVE  # Name under which the file will be saved on Google Drive

    log_info("Starting upload to Google Drive ...")
    upload_feather_to_drive(
        service_account_file=service_account_file,
        file_path=file_path,
        file_name=file_name,
        parent_folder_id=parent_folder_id,
        convert_to_google_format=False  # Set to True if conversion to Google Spreadsheet is desired (not typical for Feather files)
    )
    log_info("Upload completed.")