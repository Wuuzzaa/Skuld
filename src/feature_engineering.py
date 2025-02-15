import pandas as pd
from config import *


def feature_construction():
    # load data
    df = pd.read_csv(PATH_DATAFRAME_DATA_MERGED_CSV)

    # add new features
    print("add analyst target price - close price in USD")
    df["target-close$"] = round(df["analyst_mean_target"] - df["close"], 2)

    print("add the percent value of the delta between analyst and close price")
    df["target-close%"] = round(df["target-close$"] / df["close"] * 100, 2)

    # store data back again
    df.to_csv(PATH_DATAFRAME_DATA_MERGED_CSV, index=False)

