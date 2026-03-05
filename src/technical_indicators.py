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

SKULD_INDICATORS = ta.Study(
    name="Skuld Indicators",
    cores=0,  # Usually faster than multiprocessing
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
    ],
)


def __calc_symbol_technical_indicators(df: pd.DataFrame, verbose: bool = False) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.sort_values("snapshot_date", ascending=True, kind="stable")
    df.ta.study(SKULD_INDICATORS, verbose=verbose)

    # RSL
    df['RSL'] = df['close'] / df['close'].rolling(window=130).mean()
    return df


def _chunked(values: list, chunk_size: int):
    for i in range(0, len(values), chunk_size):
        yield values[i:i + chunk_size]


def calc_technical_indicators(verbose: bool, symbol_batch_size: int = 500):
    # 1) get all symbols
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / "get_symbolnames_asc.sql"
    df_symbols = select_into_dataframe(sql_file_path=sql_file_path)
    symbols = df_symbols["symbol"].to_list()

    # 2) batchweise OHLCV laden (weniger DB-Roundtrips) und danach pro Symbol berechnen
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / "technical_indicators_symbol_ohlcv.sql"

    for sym_batch in tqdm(list(_chunked(symbols, symbol_batch_size)), desc="Symbol-Batches"):
        params = {"symbols": sym_batch}
        df_batch = select_into_dataframe(sql_file_path=sql_file_path, params=params)

        if df_batch.empty:
            continue

        # Erwartet: SQL liefert symbol + snapshot_date, sortiert nach symbol, snapshot_date
        for symbol, df_symbol in df_batch.groupby("symbol", sort=False):
            logger.debug(f"{symbol}: rows={len(df_symbol)}")
            df_out = __calc_symbol_technical_indicators(df=df_symbol, verbose=verbose)
            pass
            #todo 3) update the database

if __name__ == "__main__":
    calc_technical_indicators(verbose=False)
    pass