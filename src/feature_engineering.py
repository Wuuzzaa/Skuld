import math
import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from config import *


def feature_construction():
    # load data
    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)

    # cast expiration_date column from int to datetime
    df["expiration_date"] = pd.to_datetime(df["expiration_date"].astype(str), format="%Y%m%d")

    # add new features
    print("add analyst target price - close price in USD")
    df["target-close$"] = round(df["analyst_mean_target"] - df["close"], 2)

    print("add the percent value of the delta between analyst and close price")
    df["target-close%"] = round(df["target-close$"] / df["close"] * 100, 2)

    print("add Days to expiration: dte")
    today = pd.Timestamp.today().normalize()
    df['dte'] = (df['expiration_date'] - today).dt.days

    print("add expected move")
    df['expected_move'] = df['close'] * df['iv'] * np.sqrt(df['dte'] / 365)

    # store data back again
    df.to_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER)

if __name__ == "__main__":
    feature_construction()
