import streamlit as st
import pandas as pd
import requests
from lxml import html
from urllib.parse import urljoin
import io
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


# -------------------- Helpers for classification --------------------
def _read_excel_sheet(content, sheet, header_row=2):
    """Read one sheet from Excel bytes and clean column names."""
    df = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=header_row)
    unnamed_cols = [c for c in df.columns if isinstance(c, str) and c.startswith("Unnamed:")]
    if unnamed_cols:
        df = df.drop(columns=unnamed_cols)
        log_info(f"Removed unnamed columns in '{sheet}': {unnamed_cols}")
    df.columns = df.columns.astype(str).str.strip().str.replace(r"\s+", "-", regex=True)
    return df

def _symbol_series(df):
    """Return normalized ticker series (UPPER, trimmed, non-empty)."""
    for col in ["Symbol", "Ticker", "Ticker-Symbol"]:
        if col in df.columns:
            s = df[col].astype(str).str.strip().str.upper()
            return s[~s.eq("")]
    # Fallback: first column
    first = df.columns[0]
    s = df[first].astype(str).str.strip().str.upper()
    return s[~s.eq("")]

def _detect_symbol_col(df):
    """Find symbol column in 'All' sheet (fallback: first column)."""
    for col in ["Symbol", "Ticker", "Ticker-Symbol"]:
        if col in df.columns:
            return col
    return df.columns[0]

def _add_classification(df_all, content):
    """
    Add 'Classification' based on membership in Champions/Contenders/Challengers.
    Priority: Champions > Contenders > Challengers > Unclassified.
    """
    try:
        df_champions   = _read_excel_sheet(content, "Champions", header_row=2)
        df_contenders  = _read_excel_sheet(content, "Contenders", header_row=2)
        df_challengers = _read_excel_sheet(content, "Challengers", header_row=2)
    except Exception as e:
        log_error(f"Error reading category sheets: {e}")
        df_all["Classification"] = "Unclassified"
        return df_all

    champions   = set(_symbol_series(df_champions))
    contenders  = set(_symbol_series(df_contenders))
    challengers = set(_symbol_series(df_challengers))

    sym_col  = _detect_symbol_col(df_all)
    norm_sym = df_all[sym_col].astype(str).str.strip().str.upper()

    cls = pd.Series("Unclassified", index=df_all.index)
    cls[norm_sym.isin(challengers)] = "Challengers"
    cls[norm_sym.isin(contenders)]  = "Contenders"
    cls[norm_sym.isin(champions)]   = "Champions"

    df_all["Classification"] = cls
    return df_all


# -------------------- Öffentliche Funktionen --------------------
def process_dividend_data(path_outputfile):
    """
    Downloads and processes the XLSX file from the dividend radar webpage,
    adds a 'Classification' column from the category tabs, displays and saves as Feather.
    """
    log_info("Starting dividend data extraction process.")
    content = download_xlsx_file()

    if not content:
        log_error("Failed to download XLSX file. Aborting process.")
        show_log_messages()
        return
    
    try:
        # Base: read 'All' sheet (header in third row)
        df = _read_excel_sheet(content, "All", header_row=2)
        log_info("Excel 'All' sheet read successfully.")
    except Exception as e:
        log_error(f"Error reading the Excel file: {e}")
        show_log_messages()
        return

    # Add classification from category tabs
    try:
        df = _add_classification(df, content)
        log_info("Classification column added.")
    except Exception as e:
        log_error(f"Error during classification: {e}")
        show_log_messages()
        return
    
    log_info(f"Columns after processing: {df.columns.tolist()}")
    log_info(f"Number of rows read: {len(df)}")
    
    st.write("DataFrame-Inhalt:")
    st.write(df)
    
    try:
        df.to_feather(str(path_outputfile))
        log_info(f"DataFrame saved as {path_outputfile}.")
    except Exception as e:
        log_error(f"Error saving as Feather: {e}") 

def force_data_download(path_outputfile):
    """
    Forces the download of dividend data and overwrites the existing Feather file.
    Adds 'Classification' from category tabs before saving.
    """
    log_info("Forcing dividend data download and overwriting the Feather file.")
    
    content = download_xlsx_file()
    if not content:
        log_error("Error downloading the XLSX file during forced download.")
        return

    try:
        df = _read_excel_sheet(content, "All", header_row=2)
        log_info("Excel 'All' sheet read successfully during forced download.")
        df = _add_classification(df, content)
        log_info("Classification column added (forced).")
    except Exception as e:
        log_error(f"Error reading/classifying during forced download: {e}")
        return

    try:
        df.to_feather(str(path_outputfile))
        log_info(f"DataFrame saved successfully as {path_outputfile} (overwritten).")
    except Exception as e:
        log_error(f"Error saving DataFrame as Feather during forced download: {e}")
