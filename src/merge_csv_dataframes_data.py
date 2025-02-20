import pandas as pd
from config import *
from google_drive_upload import upload_csv_to_drive  # <--- Import der Upload-Funktion

def merge_data_dataframes():
    print("Merge Option and Price Indicators Data")
    df_option_data = pd.read_csv(PATH_DATAFRAME_OPTION_DATA_CSV)
    df_price_indicators = pd.read_csv(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_CSV)
    df_merged = pd.merge(df_option_data, df_price_indicators, how='left', left_on='symbol', right_on='symbol')

    print("Join Yahoo Finance Analyst Price targets")
    df_price_targets = pd.read_csv(PATH_DATAFRAME_DATA_ANALYST_PRICE_TARGET_CSV)
    df_merged = pd.merge(df_merged, df_price_targets, how='left', left_on='symbol', right_on='symbol')

    print(f"Store merged to: {PATH_DATAFRAME_DATA_MERGED_CSV}")
    df_merged[DATAFRAME_DATA_MERGED_COLUMNS].to_csv(PATH_DATAFRAME_DATA_MERGED_CSV, index=False)

    # ----------------------------
    # UPLOAD SCHRITT
    # ----------------------------
    print("Starte Upload zur Google Drive ...")
    service_account_file = "service_account.json"  # oder wie du ihn nennst
    parent_folder_id = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"  # Deine Ordner-ID
    upload_csv_to_drive(
        service_account_file=service_account_file,
        file_path=PATH_DATAFRAME_DATA_MERGED_CSV,
        file_name="merged_data.csv",  # Name in Drive
        parent_folder_id=parent_folder_id,
        convert_to_google_format=False  # True, falls du es in Google Spreadsheet konvertieren möchtest
    )
    print("Upload beendet.")
