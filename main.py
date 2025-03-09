from src.feature_engineering import feature_construction, type_casting
from src.optiondata_feathers_to_df_merge import combine_feather_files
from src.tradingview_optionchain_scrapper import scrape_option_data
from src.price_and_technical_analysis_data_scrapper import scrape_and_save_price_and_technical_indicators
from src.merge_feather_dataframes_data import merge_data_dataframes
from src.util import create_all_project_folders, get_option_expiry_dates
from src.yfinance_analyst_price_targets import scrape_yahoo_finance_analyst_price_targets
from config import *
from src.google_drive_upload import upload_merged_data
from src.dividend_radar import process_dividend_data


def main(testmode=True):
    create_all_project_folders()

    print("#"*80)
    print("Get Yahoo Finance data")
    print("#" * 80)
    if testmode:
        scrape_yahoo_finance_analyst_price_targets(SYMBOLS[:3])
    else:
        scrape_yahoo_finance_analyst_price_targets(SYMBOLS)
    print("Get Yahoo Finance data - Done")

    print("#" * 80)
    print("Get option data")
    print("#" * 80)

    if testmode:
        for expiration_date in get_option_expiry_dates()[:3]:
            for symbol in SYMBOLS[:3]:
                scrape_option_data(symbol=symbol, expiration_date=expiration_date, exchange=SYMBOLS_EXCHANGE[symbol], folderpath=PATH_OPTION_DATA_TRADINGVIEW)
    else:
        for expiration_date in get_option_expiry_dates():
            for symbol in SYMBOLS:
                scrape_option_data(symbol=symbol, expiration_date=expiration_date, exchange=SYMBOLS_EXCHANGE[symbol], folderpath=PATH_OPTION_DATA_TRADINGVIEW)

    print("Get option data - Done")
    print("#" * 80)
    print("Combine option data JSON to feather")
    print("#" * 80)
    combine_feather_files(folder_path=PATH_OPTION_DATA_TRADINGVIEW, data_feather_path=PATH_DATAFRAME_OPTION_DATA_FEATHER)
    print("Combine option data JSON to feather - Done")

    print("#" * 80)
    print("Get price and technical indicators")
    print("#" * 80)
    scrape_and_save_price_and_technical_indicators(PATH_DATAFRAME_PRICE_AND_INDICATOR_DATA_FEATHER)
    print("Get price and technical indicators - Done")

    print("#" * 80)
    print("Dividend Radar")
    print("#" * 80)
    process_dividend_data(path_outputfile=PATH_DIVIDEND_RADAR)
    print("Dividend Radar Done") 

    print("#" * 80)
    print("Merge all feather dataframe files")
    print("#" * 80)
    merge_data_dataframes()
    print("Merge all feather dataframe files - Done")

    print("#" * 80)
    print("Feature engineering")
    print("#" * 80)
    feature_construction()
    type_casting()
    print("Feature engineering - Done") 

    # Upload the merged Feather file to Google Drive after feature construction is completed
    print("#" * 80)
    print("Upload file to Google Drive")
    print("#" * 80)
    upload_merged_data() 
    print("Upload file to Google Drive - Done")

    print("RUN DONE")


if __name__ == '__main__':
    main()



