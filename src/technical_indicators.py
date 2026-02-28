import pandas as pd
import pandas_ta as ta
import logging
import os
from src.logger_config import setup_logging
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe
from tqdm import tqdm
from src.util import get_dataframe_memory_usage


# enable logging
setup_logging(component="technical_indicators", log_level=logging.DEBUG, console_output=True) #todo component in production anpassen
logger = logging.getLogger(os.path.basename(__file__))
logger.debug(f"Start: {os.path.basename(__file__)}")

# Debuginfo
# print(ta.AllStudy)
# print(ta.CommonStudy)

# ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

def __calc_symbol_technical_indicators(symbol, study, verbose=False):
    logger.debug(f"Calculating Technical Indicators for symbol: {symbol}")

    params = {
        "symbol": symbol,
    }

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'technical_indicators_symbol_ohlcv.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path, params=params)


    df.ta.study(study, verbose=verbose)

    # Do not use slow as fuck :D
    #df.ta.study(ta.AllStudy)

    return df

def calc_technical_indicators(verbose):
    study = ta.Study(
        name="Skuld Indicators",
        cores=0, # Usually faster than multiprocessing
        ta=[
            {"kind": "ema", "length": 5},
            {"kind": "ema", "length": 10},
            {"kind": "ema", "length": 20},
            {"kind": "ema", "length": 30},
            {"kind": "ema", "length": 50},
            {"kind": "ema", "length": 100},
            {"kind": "ema", "length": 200},
            {"kind": "sma", "length": 5},
            {"kind": "sma", "length": 10},
            {"kind": "sma", "length": 20},
            {"kind": "sma", "length": 30},
            {"kind": "sma", "length": 50},
            {"kind": "sma", "length": 100},
            {"kind": "sma", "length": 200},
            {"kind": "macd"},
            {"kind": "bbands", "length": 20},
            {"kind": "atr", "length": 14},
            {"kind": "adx", "length": 10},
            {"kind": "stoch", "k": 14, "d": 3, "smooth_k": 1},
            {"kind": "rsi", "length": 14},
        ]
    )

    # 1. get all symbols
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'get_symbolnames_asc.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path)
    symbols = df["symbol"].to_list()

    # 2. calculate the technical indicators for each symbol
    for symbol in tqdm(symbols, desc="calculate the technical indicators for each symbol"):
        df = __calc_symbol_technical_indicators(symbol=symbol, study=study, verbose=verbose)

        # 3. update the database
        # todo



if __name__ == "__main__":
    calc_technical_indicators(verbose=False)
    pass