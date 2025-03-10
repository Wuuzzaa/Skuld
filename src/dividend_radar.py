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
    
    This function fetches the webpage at 
    "https://www.portfolio-insight.com/dividend-radar", extracts the first XLSX link using XPath,
    and returns the file content as bytes.
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
    log_info("Starting dividend data extraction process.")
    content = download_xlsx_file()

    if not content:
        log_error("Failed to download XLSX file. Aborting process.")
        show_log_messages()
        return
    
    try:
        # Read the "All" sheet, assuming the header is in the third row (header index 2)
        # Maybe this need to be changed in the feature due to file changes or similar
        df = pd.read_excel(io.BytesIO(content), sheet_name="All", header=2)
        log_info("Excel file read successfully.")

    except Exception as e:
        log_error(f"Error reading the Excel file: {e}")
        show_log_messages()
        return
    
    # Remove unnecessary columns (e.g. columns that start with "Unnamed:")
    unnamed_cols = [col for col in df.columns if col.startswith("Unnamed:")]
    if unnamed_cols:
        df.drop(columns=unnamed_cols, inplace=True)
        log_info(f"Removed unnamed columns: {unnamed_cols}")
    
    # Clean column names by stripping whitespace.
    df.columns = df.columns.str.strip()
    log_info("Cleaned column names.")
    
    log_info(f"Columns after processing: {df.columns.tolist()}")
    log_info(f"Number of rows read: {len(df)}")

    # Save the DataFrame as a Feather file using the provided output path.
    try:
        df.to_feather(str(path_outputfile))
        log_info(f"DataFrame saved as {path_outputfile}.")

    except Exception as e:
        log_error(f"Error saving as Feather: {e}")
    