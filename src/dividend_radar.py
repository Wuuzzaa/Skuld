import streamlit as st
import pandas as pd
import requests
from lxml import html
from urllib.parse import urljoin
import io
from config import *
from src.custom_logging import log_info, log_error, log_write, show_log_messages


def download_xlsx_file():
    """
    Downloads the XLSX file from the dividend radar webpage.
    """
    page_url = URL_DIVIDEND_RADAR
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(page_url, headers=headers)
    
    if response.status_code != 200:
        log_error(f"Error loading the webpage. Status code: {response.status_code}")
        return None
    
    log_info("Webpage loaded successfully.")
    
    # Parse the HTML and find the first .xlsx link via XPath.
    tree = html.fromstring(response.content)
    file_url = tree.xpath('(//a[contains(@href, ".xlsx")])[1]/@href')
    
    if not file_url:
        log_error("No XLSX download link found.")
        return None
    
    file_url = file_url[0]
    if file_url.startswith("/"):
        file_url = urljoin(page_url, file_url)
    
    log_info(f"Found XLSX URL: {file_url}")
    
    # Download the XLSX file.
    file_response = requests.get(file_url)
    if file_response.status_code != 200:
        log_error("Error downloading the XLSX file.")
        return None
    
    log_info("XLSX file downloaded successfully.")
    return file_response.content


def process_dividend_data(path_outputfile):
    """
    Downloads and processes the XLSX file from the dividend radar webpage,
    then displays the processed DataFrame and saves it as a Feather file.
    """
    log_info("Starting dividend data extraction process.")
    content = download_xlsx_file()

    if not content:
        log_error("Failed to download XLSX file. Aborting process.")
        show_log_messages()
        return
    
    try:
        # Read the "All" sheet, assuming the header is in the third row (header index 2).
        df = pd.read_excel(io.BytesIO(content), sheet_name="All", header=2)
        log_info("Excel file read successfully.")

    except Exception as e:
        log_error(f"Error reading the Excel file: {e}")
        show_log_messages()
        return
    
    # Remove columns that start with "Unnamed:".
    unnamed_cols = [col for col in df.columns if col.startswith("Unnamed:")]
    if unnamed_cols:
        df.drop(columns=unnamed_cols, inplace=True)
        log_info(f"Removed unnamed columns: {unnamed_cols}")
    
    # Clean column names by stripping whitespace and replacing internal spaces with dashes.
    df.columns = df.columns.str.strip().str.replace(r"\s+", "-", regex=True)
    log_info("Cleaned column names (replaced whitespace with dashes).")
    
    log_info(f"Columns after processing: {df.columns.tolist()}")
    log_info(f"Number of rows read: {len(df)}")
    
    # Alternative Darstellung: Verwende st.write(df) zur Anzeige des DataFrames.
    st.write("DataFrame-Inhalt:")
    st.write(df)
    
    # Save the DataFrame as a Feather file using the provided output path.
    try:
        df.to_feather(str(path_outputfile))
        log_info(f"DataFrame saved as {path_outputfile}.")

    except Exception as e:
        log_error(f"Error saving as Feather: {e}") 

def force_data_download(path_outputfile):
    """
    Forces the download of dividend data and overwrites the existing Feather file.
    This function can be called from another Python module (e.g., as a callback for a Streamlit button).
    """
    log_info("Forcing dividend data download and overwriting the Feather file.")
    
    content = download_xlsx_file()
    if not content:
        log_error("Error downloading the XLSX file during forced download.")
        return

    try:
        # Read the "All" sheet, assuming the header is in the third row (index 2).
        df = pd.read_excel(io.BytesIO(content), sheet_name="All", header=2)
        log_info("Excel file read successfully during forced download.")
    except Exception as e:
        log_error(f"Error reading the Excel file during forced download: {e}")
        return

    # Remove columns whose names start with "Unnamed:".
    unnamed_cols = [col for col in df.columns if col.startswith("Unnamed:")]
    if unnamed_cols:
        df.drop(columns=unnamed_cols, inplace=True)
        log_info(f"Removed 'Unnamed' columns: {unnamed_cols}")

    # Clean column names by stripping whitespace and replacing internal spaces with hyphens.
    df.columns = df.columns.str.strip().str.replace(r"\s+", "-", regex=True)
    log_info("Cleaned column names during forced download.")

    # Save the DataFrame as a Feather file, overwriting the existing file if necessary.
    try:
        df.to_feather(str(path_outputfile))
        log_info(f"DataFrame saved successfully as {path_outputfile} (overwritten).")
    except Exception as e:
        log_error(f"Error saving DataFrame as Feather during forced download: {e}")

