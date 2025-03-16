from config import *
import pandas as pd


def filter_dataframe(df, RSI_long=None, RSI_short=None, BB=None, Stoch_long=None, Stoch_short=None, VWMA=None,
                     MACD=None, ADX=None):
    """
    Filters the given DataFrame based on the provided technical indicators and
    adds individual columns for each filter condition to enhance transparency.

    Parameters:
    - df: DataFrame containing market data
    - RSI_long: int or None, threshold for RSI long signals (e.g., 30)
    - RSI_short: int or None, threshold for RSI short signals (e.g., 70)
    - BB: bool or None, if True, applies Bollinger Bands conditions
    - Stoch_long: int or None, threshold for Stochastic K long signals (e.g., 20)
    - Stoch_short: int or None, threshold for Stochastic K short signals (e.g., 80)
    - VWMA: bool or None, if True, applies VWMA conditions
    - MACD: bool or None, if True, applies MACD conditions
    - ADX: int or None, if set, filters based on ADX values

    Returns:
    - A filtered DataFrame with long and short trading signals and columns indicating
      whether each condition was met.
    """

    # Create a copy of the DataFrame to avoid modifying the original data
    df = df.copy()

    # Initialize condition tracking columns
    df["RSI_long_condition"] = False
    df["RSI_short_condition"] = False
    df["BB_long_condition"] = False
    df["BB_short_condition"] = False
    df["Stoch_long_condition"] = False
    df["Stoch_short_condition"] = False
    df["VWMA_long_condition"] = False
    df["VWMA_short_condition"] = False
    df["MACD_long_condition"] = False
    df["MACD_short_condition"] = False
    df["ADX_condition"] = df["ADX"] > 20  # Default ADX filter

    # Lists to store conditions for long (buy) and short (sell) signals
    long_conditions = []
    short_conditions = []

    # RSI Filter
    if RSI_long is not None:
        df["RSI_long_condition"] = df["RSI"] < RSI_long
        long_conditions.append(df["RSI_long_condition"])

    if RSI_short is not None:
        df["RSI_short_condition"] = df["RSI"] > RSI_short
        short_conditions.append(df["RSI_short_condition"])

    # Bollinger Bands Filter
    if BB is not None and BB:
        df["BB_long_condition"] = df["close"] < df["BB.lower"]
        df["BB_short_condition"] = df["close"] > df["BB.upper"]
        long_conditions.append(df["BB_long_condition"])
        short_conditions.append(df["BB_short_condition"])

    # Stochastic Oscillator Filter
    if Stoch_long is not None:
        df["Stoch_long_condition"] = df["Stoch.K"] < Stoch_long
        long_conditions.append(df["Stoch_long_condition"])

    if Stoch_short is not None:
        df["Stoch_short_condition"] = df["Stoch.K"] > Stoch_short
        short_conditions.append(df["Stoch_short_condition"])

    # VWMA Filter
    if VWMA is not None and VWMA:
        df["VWMA_long_condition"] = df["close"] < df["VWMA"] * 0.98
        df["VWMA_short_condition"] = df["close"] > df["VWMA"] * 1.02
        long_conditions.append(df["VWMA_long_condition"])
        short_conditions.append(df["VWMA_short_condition"])

    # MACD Filter
    if MACD is not None and MACD:
        df["MACD_long_condition"] = df["MACD.macd"] > 0
        df["MACD_short_condition"] = df["MACD.macd"] < 0
        long_conditions.append(df["MACD_long_condition"])
        short_conditions.append(df["MACD_short_condition"])

    # ADX Filter: Apply only if a specific threshold is given
    if ADX is not None:
        df["ADX_condition"] = df["ADX"] > ADX

    # Generate trade signals: At least 3 conditions must be met
    df["long_signal"] = (sum(long_conditions) >= 3) if long_conditions else False
    df["short_signal"] = (sum(short_conditions) >= 3) if short_conditions else False

    # **Final filtering step:** Keep only rows where ADX is valid AND either long or short signal is true
    df = df[(df["ADX_condition"]) & (df["long_signal"] | df["short_signal"])]

    return df


if __name__ == "__main__":
    # Load data from the feather file, selecting relevant columns
    df = pd.read_feather(PATH_DATAFRAME_DATA_MERGED_FEATHER, columns=[
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "RSI",
        "Stoch.K",
        "ADX",
        "MACD.macd",
        "VWMA",
        "BB.lower",
        "BB.upper"
    ]).drop_duplicates()

    # Example usage with filtering:
    filtered_df = filter_dataframe(
        df,
        RSI_long=30,
        RSI_short=70,
        BB=True,
        Stoch_long=20,
        Stoch_short=80,
        VWMA=True,
        MACD=True,
        ADX=25
    )

    # Display a sample of the filtered data
    print(filtered_df.head())
