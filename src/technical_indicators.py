import pandas as pd
import pandas_ta as ta
import logging
import os
from src.logger_config import setup_logging
from config import PATH_DATABASE_QUERY_FOLDER, TABLE_TECHNICAL_INDICATORS
from src.database import get_postgres_engine, insert_into_table, select_into_dataframe, truncate_table, insert_into_table_bulk
from tqdm import tqdm


# enable logging
setup_logging(component="technical_indicators", log_level=logging.DEBUG, console_output=True) #todo component in production anpassen
logger = logging.getLogger(__name__)
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

def calc_technical_indicators(symbols, verbose: bool = False, symbol_batch_size: int = 500):

    # batchweise OHLCV laden (weniger DB-Roundtrips) und danach pro Symbol berechnen
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / "technical_indicators_symbol_ohlcv.sql"

    with get_postgres_engine().begin() as connection:
        truncate_table(connection, TABLE_TECHNICAL_INDICATORS)
        for sym_batch in tqdm(list(_chunked(symbols, symbol_batch_size)), desc="Symbol-Batches"):
            params = {"symbols": sym_batch}
            df_batch = select_into_dataframe(sql_file_path=sql_file_path, params=params)

            if df_batch.empty:
                continue
            
            batch_results_list = []
            # Erwartet: SQL liefert symbol + snapshot_date, sortiert nach symbol, snapshot_date
            for symbol, df_symbol in df_batch.groupby("symbol", sort=False):
                logger.debug(f"{symbol}: rows={len(df_symbol)}")
                df_out = __calc_symbol_technical_indicators(df=df_symbol, verbose=verbose)
                df_out = df_out.drop(columns=['snapshot_date', 'open', 'high', 'low', 'close', 'volume'])
                
                latest_row = df_out.tail(1)
                batch_results_list.append(latest_row)
            
            if batch_results_list:
                df_to_insert = pd.concat(batch_results_list, ignore_index=False)

                # --- Database Persistence ---
                insert_into_table(
                    connection,
                    table_name=TABLE_TECHNICAL_INDICATORS,
                    dataframe=df_to_insert,
                    if_exists="append"
                )

def calc_technical_indicators_history(symbols, verbose: bool = False, symbol_batch_size: int = 500):
    table_name = f"{TABLE_TECHNICAL_INDICATORS}HistoryDaily"
    # batchweise OHLCV laden (weniger DB-Roundtrips) und danach pro Symbol berechnen
    sql_file_path = PATH_DATABASE_QUERY_FOLDER / "technical_indicators_symbol_ohlcv_history.sql"

    total_rows = 0
    connection = get_postgres_engine().raw_connection()
    try:
        truncate_table(connection, table_name)
        for sym_batch in tqdm(list(_chunked(symbols, symbol_batch_size)), desc="Symbol-Batches"):
            params = {"symbols": sym_batch}
            df_batch = select_into_dataframe(sql_file_path=sql_file_path, params=params)

            if df_batch.empty:
                continue
            
            batch_results_list = []
            # Erwartet: SQL liefert symbol + snapshot_date, sortiert nach symbol, snapshot_date
            for symbol, df_symbol in df_batch.groupby("symbol", sort=False):
                logger.debug(f"{symbol}: rows={len(df_symbol)}")
                df_out = __calc_symbol_technical_indicators(df=df_symbol, verbose=verbose)
                df_out = df_out.drop(columns=['open', 'high', 'low', 'close', 'volume'])
                
                batch_results_list.append(df_out)
            
            if batch_results_list:
                df_to_insert = pd.concat(batch_results_list, ignore_index=False)

                # --- Database Persistence ---
                insert_into_table_bulk(
                    connection,
                    table_name=table_name,
                    dataframe=df_to_insert,
                    if_exists="append"
                )
                total_rows += len(df_to_insert)
        connection.commit()
    finally:
        connection.close()
    logger.info(f"Total historical technical indicators calculated: {total_rows}")

    
if __name__ == "__main__":
    calc_technical_indicators_history(verbose=False)
    pass