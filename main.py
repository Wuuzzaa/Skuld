import argparse
from src.feature_engineering import feature_construction
from src.optiondata_feathers_to_df_merge import combine_feather_files
from src.tradingview_optionchain_scrapper import scrape_option_data
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.merge_feather_dataframes_data import merge_data_dataframes
from src.util import create_all_project_folders, get_option_expiry_dates
from src.yahooquery_earning_dates import scrape_earning_dates
from src.yahooquery_option_chain import get_yahooquery_option_chain
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *
from src.google_drive_upload import upload_merged_data
from src.dividend_radar import process_dividend_data
from config_utils import validate_config




def main(upload_df_google_drive=True):
    print("#" * 80)
    
    active_mode = validate_config()
    print(f"[INFO] Aktiver Modus: {active_mode}")
    if active_mode == "GENERAL_TEST_MODE":
        print(f"[INFO] Max Symbole: {GENERAL_TEST_MODE_MAX_SYMBOLS}, Max Expiry Dates: {GENERAL_TEST_MODE_MAX_EXPIRY_DATES}")
    print(f"upload_df_google_drive: {upload_df_google_drive}\n")
    print("#" * 80)

    create_all_project_folders()

    print("#"*80)
    print("Get Yahoo Finance data")
    print("#" * 80)
    scrape_yahoo_finance_analyst_price_targets()
    print("Get Yahoo Finance data - Done")

    print("#" * 80)
    print("Get option data")
    print("#" * 80)

    # NEW: Config-driven data collection instead of hardcoded testmode
    expiry_dates = get_option_expiry_dates()
    symbols_to_use = SYMBOLS
    
    # Apply config-based limitations
    if GENERAL_TEST_MODE_ENABLED:
        print("[CONFIG] Aktiver Modus: GENERAL TEST MODE")
        expiry_dates = expiry_dates[:GENERAL_TEST_MODE_MAX_EXPIRY_DATES]
        symbols_to_use = SYMBOLS[:GENERAL_TEST_MODE_MAX_SYMBOLS]
        print(f"GENERAL TEST MODE: Limited to {len(symbols_to_use)} symbols and {len(expiry_dates)} expiry dates")
    else:
        print("[CONFIG] Aktiver Modus: PRODUKTIV (kein Testmode)")

    print(f"Collecting data for {len(symbols_to_use)} symbols and {len(expiry_dates)} expiry dates")
    
    for expiration_date in expiry_dates:
        for symbol in symbols_to_use:
            scrape_option_data(
                symbol=symbol,
                expiration_date=expiration_date,
                exchange=SYMBOLS_EXCHANGE[symbol],
                folderpath=PATH_OPTION_DATA_TRADINGVIEW
            )

    print("Get option data - Done")

    print("#" * 80)
    print("Combine option data JSON to feather")
    print("#" * 80)
    combine_feather_files(folder_path=PATH_OPTION_DATA_TRADINGVIEW, data_feather_path=PATH_DATAFRAME_OPTION_DATA_FEATHER)
    print("Combine option data JSON to feather - Done")

    print("#" * 80)
    print("Get price and technical indicators")
    print("#" * 80)
    scrape_and_save_price_and_technical_indicators()
    print("Get price and technical indicators - Done")

    print("#" * 80)
    print("Dividend Radar")
    print("#" * 80)
    process_dividend_data(path_outputfile=PATH_DIVIDEND_RADAR)
    # Debug: Check if Classification exists in dividend data
    df_div = pd.read_feather(PATH_DIVIDEND_RADAR)
    print("Dividend Radar columns:", df_div.columns.tolist())
    print("Has Classification?", 'Classification' in df_div.columns)
    if 'Classification' in df_div.columns:
        print("Classification values:", df_div['Classification'].value_counts())
    print("Dividend Radar Done")

    print("#" * 80)
    print("Earning Dates")
    print("#" * 80)
    scrape_earning_dates()
    print("Earning Dates Done")

    print("#" * 80)
    print("Yahooquery Option Chain")
    print("#" * 80)
    get_yahooquery_option_chain()
    print("Yahooquery Option Chain Done")

    print("#" * 80)
    print("Merge all feather dataframe files")
    print("#" * 80)
    merge_data_dataframes()
    # Debug: Check merged data
    df_merged = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)
    print("Final columns:", df_merged.columns.tolist())
    print("Has Classification?", 'Classification' in df_merged.columns)
    print("Merge all feather dataframe files - Done")

    print("#" * 80)
    print("Feature engineering")
    print("#" * 80)
    feature_construction()
    #type_casting()
    print("Feature engineering - Done")



    if upload_df_google_drive:
        print("#" * 80)
        print("Upload file to Google Drive")
        print("#" * 80)
        upload_merged_data()
        print("Upload file to Google Drive - Done")

    print("RUN DONE")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Run the main script with optional parameters.")
    parser.add_argument("--testmode", type=lambda x: x.lower() == 'true', default=False,
                        help="Run in test mode (default: False)")
    parser.add_argument("--upload_df_google_drive", type=lambda x: x.lower() == 'true', default=True,
                        help="Upload data to Google Drive (default: True)")

    args = parser.parse_args()
    main(upload_df_google_drive=args.upload_df_google_drive)
