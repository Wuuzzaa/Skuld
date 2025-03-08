import os
import io
import json
import streamlit as st
import pandas as pd
from datetime import datetime, time
from zoneinfo import ZoneInfo
from src.custom_logging import log_info, log_error, log_write

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from config import PATH_DATAFRAME_DATA_MERGED_FEATHER , FILENAME_GOOGLE_DRIVE, PATH_ON_GOOGLE_DRIVE, PATH_FOR_SERVICE_ACCOUNT_FILE  

"""
Configuration:
- Local storage location for the Feather file.
- The file on Google Drive is now in Feather format.
- Google Drive folder ID, local timezone, and update times (in local timezone).
"""
PATH_DATAFRAME_DATA_MERGED_FEATHER = PATH_DATAFRAME_DATA_MERGED_FEATHER
FILE_NAME = FILENAME_GOOGLE_DRIVE
PARENT_FOLDER_ID = PATH_ON_GOOGLE_DRIVE
LOCAL_TZ = "Europe/Berlin"
UPDATE_TIMES = [time(10, 15), time(16, 15)]

def get_credentials():
    """Reads the Service Account credentials from Streamlit secrets (in the [service_account] section)
    and creates a Credentials object.
    """
    service_account_dict = st.secrets["service_account"]
    return service_account.Credentials.from_service_account_info(
        service_account_dict,
        scopes=["https://www.googleapis.com/auth/drive"]
    )

def find_file_id_by_name(file_name, parent_folder_id=None):
    """Searches for a file with the given name on Google Drive and returns its ID.
    Optionally restricts the search to a specific folder.
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
            log_error("No file found with the specified name.")
            return None
        else:
            file = files[0]
            log_info(f"Found file: {file.get('name')} (ID: {file.get('id')})")
            return file.get("id")
    except HttpError as error:
        log_error(f"An error occurred: {error}")
        return None

def download_feather_from_drive(file_id):
    """Downloads the Feather file from Google Drive.
    Returns a BytesIO stream containing the file.
    """
    try:
        creds = get_credentials()
        service = build("drive", "v3", credentials=creds)
        file_info = service.files().get(
            fileId=file_id,
            fields="id, name, mimeType, modifiedTime"
        ).execute()
        mime_type = file_info.get("mimeType", "")
        modified_time_str = file_info.get("modifiedTime")
        if modified_time_str:
            modified_time_utc = datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
            modified_time_local = modified_time_utc.astimezone(ZoneInfo(LOCAL_TZ))
            log_info(f"File last modified (Google Drive): {modified_time_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        # Directly download the file without export since it's a Feather file
        request = service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                log_write(f"Download progress: {int(status.progress() * 100)}%")
        file_stream.seek(0)
        return file_stream
    except HttpError as error:
        log_error(f"An error occurred: {error}")
        return None

def get_update_datetime(local_update_time: time, tz_name=LOCAL_TZ) -> datetime:
    """Creates a timezone-aware datetime for the given update time (e.g. 10:15 or 16:15)
    in the local timezone and converts it to UTC.
    """
    today_local = datetime.now(ZoneInfo(tz_name)).date()
    local_dt = datetime.combine(today_local, local_update_time, tzinfo=ZoneInfo(tz_name))
    return local_dt.astimezone(ZoneInfo("UTC"))

def file_last_modified(path) -> datetime:
    """Returns the last modification time of the file as a timezone-aware UTC datetime.
    """
    return datetime.fromtimestamp(os.path.getmtime(path), tz=ZoneInfo("UTC"))

def should_update_file(local_file, update_times, tz_name=LOCAL_TZ) -> bool:
    """Determines whether the local file should be updated.
    Logic:
      - If the file does not exist, it must be updated.
      - On weekdays (Mon-Fri), checks if one of the defined update times (in CET) has passed
        and if the file was last modified before that time.
    """
    if not os.path.exists(local_file):
        return True
    last_mod = file_last_modified(local_file)
    now = datetime.now(ZoneInfo("UTC"))
    if now.weekday() < 6:
        for ut in update_times:
            update_dt_utc = get_update_datetime(ut, tz_name)
            if now >= update_dt_utc and last_mod < update_dt_utc:
                return True
    return False

@st.cache_data(ttl=1800, show_spinner="Loading updated data...")
def load_updated_data():
    """Loads data in Feather format. If the local file is outdated, downloads the Feather file from Google Drive,
    reads it into a DataFrame, and saves it locally. Otherwise, loads the local file.
    """
    if should_update_file(PATH_DATAFRAME_DATA_MERGED_FEATHER, UPDATE_TIMES):
        log_info("New file available – starting download from Google Drive ...")
        file_id = find_file_id_by_name(FILE_NAME, PARENT_FOLDER_ID)
        if file_id is None:
            log_error("File with the specified name was not found on Google Drive.")
            return None
        file_stream = download_feather_from_drive(file_id)
        if file_stream is None:
            return None
        os.makedirs(os.path.dirname(PATH_DATAFRAME_DATA_MERGED_FEATHER), exist_ok=True)
        # Read Feather from the downloaded stream
        try:
            df = pd.read_feather(file_stream)
            log_info("Feather file successfully read from the downloaded stream.")
        except Exception as e:
            log_error(f"Error reading the Feather file: {e}")
            return None
        # Save the DataFrame as a local Feather file
        try:
            df.to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
            log_info("Downloaded Feather file saved locally.")
        except Exception as e:
            log_error(f"Error saving the Feather file: {e}")
            return None
        return df
    else:
        log_info("Loading local Feather file ...")
        try:
            df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
            last_mod = file_last_modified(PATH_DATAFRAME_DATA_MERGED_FEATHER)
            last_mod_local = last_mod.astimezone(ZoneInfo(LOCAL_TZ))
            log_info(f"Local file last modified on: {last_mod_local.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return df
        except Exception as e:
            log_error(f"Error reading the local Feather file: {e}")
            return None
