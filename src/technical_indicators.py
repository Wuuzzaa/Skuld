import pandas as pd
import pandas_ta as ta
from config import PATH_DATABASE_QUERY_FOLDER
from src.database import select_into_dataframe


# print(ta.AllStudy)
# print(ta.CommonStudy)


# ensure logfile gets all columns of wide dataframes
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)

def calc_symbol_technical_indicators(symbol):
    params = {
        "symbol": symbol,
    }

    sql_file_path = PATH_DATABASE_QUERY_FOLDER / 'technical_indicators_symbol_ohlcv.sql'
    df = select_into_dataframe(sql_file_path=sql_file_path, params=params)

    # beispiel via yahoo download als dataframe
    # _df = pd.DataFrame()
    # df = _df.ta.ticker("spy", period="5y")

    skuld_indicators = ta.Study(
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
    df.ta.study(skuld_indicators, verbose=True)

    #df.ta.study(ta.AllStudy)  # errors slow as fuck

    # print(df.head(30))
    # print(df.tail(30))


for i in range(1000):
    calc_symbol_technical_indicators(symbol='MSFT')