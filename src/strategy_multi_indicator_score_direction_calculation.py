from config import *
import pandas as pd


def calc_multi_indicator_score_direction(
        df,
        RSI_long=None,
        RSI_short=None,
        BB=None,
        Stoch_long=None,
        Stoch_short=None,
        VWMA=None,
        MACD=None,
        ADX=None,
        min_score=3
):
    """
    Filters the given DataFrame based on the provided technical indicators and adds a scoring system.

    Parameters:
    - df: DataFrame containing market data
    - RSI_long: int or None, threshold for RSI long signals (e.g., 30)
    - RSI_short: int or None, threshold for RSI short signals (e.g., 70)
    - BB: bool or None, if True, applies Bollinger Bands conditions
    - Stoch_long: int or None, threshold for Stochastic K long signals (e.g., 20)
    - Stoch_short: int or None, threshold for Stochastic K short signals (e.g., 80)
    - VWMA: bool or None, if True, applies VWMA conditions
    - MACD: bool or None, if True, applies MACD conditions
    - ADX: int or None, optional threshold for ADX values
    - min_score: int, minimum number of conditions that must be met to keep a row

    Returns:
    - A filtered DataFrame with individual condition columns and scoring system.
    """
    df = df.copy()

    # Initialize condition tracking columns
    df["RSI_long_condition"] = (df["RSI"] < RSI_long) if RSI_long is not None else False
    df["RSI_short_condition"] = (df["RSI"] > RSI_short) if RSI_short is not None else False
    df["BB_long_condition"] = (df["close"] < df["BB.lower"]) if BB else False
    df["BB_short_condition"] = (df["close"] > df["BB.upper"]) if BB else False
    df["Stoch_long_condition"] = (df["Stoch.K"] < Stoch_long) if Stoch_long is not None else False
    df["Stoch_short_condition"] = (df["Stoch.K"] > Stoch_short) if Stoch_short is not None else False
    df["VWMA_long_condition"] = (df["close"] < df["VWMA"] * 0.98) if VWMA else False
    df["VWMA_short_condition"] = (df["close"] > df["VWMA"] * 1.02) if VWMA else False
    df["MACD_long_condition"] = (df["MACD.macd"] > 0) if MACD else False
    df["MACD_short_condition"] = (df["MACD.macd"] < 0) if MACD else False
    df["ADX_condition"] = (df["ADX"] > ADX) if ADX is not None else False

    # Calculate score based on fulfilled conditions
    df["score_long"] = df[[
        "RSI_long_condition", "BB_long_condition", "Stoch_long_condition", "VWMA_long_condition", "MACD_long_condition"
    ]].sum(axis=1) + (df["ADX_condition"] if ADX is not None else 0)

    df["score_short"] = df[[
        "RSI_short_condition", "BB_short_condition", "Stoch_short_condition", "VWMA_short_condition",
        "MACD_short_condition"
    ]].sum(axis=1) + (df["ADX_condition"] if ADX is not None else 0)

    # Apply filtering based on minimum score requirement
    df = df[(df["score_long"] >= min_score) | (df["score_short"] >= min_score)].reset_index(drop=True)

    return df


if __name__ == "__main__":
    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER, columns=[
        "symbol", "open", "high", "low", "close", "RSI", "Stoch.K", "ADX", "MACD.macd", "VWMA", "BB.lower", "BB.upper"
    ]).drop_duplicates()

    filtered_df = calc_multi_indicator_score_direction(
        df,
        RSI_long=30,
        RSI_short=70,
        BB=True,
        Stoch_long=20,
        Stoch_short=80,
        VWMA=True,
        MACD=True,
        ADX=25,
        min_score=3
    )

    print(filtered_df.head())
