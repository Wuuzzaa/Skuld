"""Covered Call Screener - PowerOptions-style calculations.

Calculates: Net Debit, Assigned Return, Annualized Return, Downside Protection.
Filters: Earnings avoidance, technical indicators, liquidity.
"""

import pandas as pd
import numpy as np
import logging
import os

logger = logging.getLogger(os.path.basename(__file__))


def calc_covered_calls(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate PowerOptions-style covered call metrics.

    Net Debit = Stock Price - Premium (cost basis per share)
    Assigned Return = (Strike + Premium - Stock Price) / Net Debit
    Annualized Return = Assigned Return * (365 / DTE)
    Downside Protection = Premium / Stock Price
    """
    if df.empty:
        return df

    df = df.copy()

    # Net Debit (cost basis if you buy stock and sell call)
    df['net_debit'] = df['stock_price'] - df['premium']

    # Assigned Return (profit if called away at strike)
    df['assigned_return'] = np.where(
        df['net_debit'] > 0,
        (df['strike_price'] + df['premium'] - df['stock_price']) / df['net_debit'],
        0
    )

    # Annualized Return
    df['annualized_return'] = np.where(
        df['DTE'] > 0,
        df['assigned_return'] * (365 / df['DTE']),
        0
    )

    # Downside Protection (premium as % of stock price)
    df['downside_protection'] = np.where(
        df['stock_price'] > 0,
        df['premium'] / df['stock_price'],
        0
    )

    # Moneyness (how deep ITM the call is)
    df['moneyness'] = np.where(
        df['stock_price'] > 0,
        (df['stock_price'] - df['strike_price']) / df['stock_price'],
        0
    )

    # Filter out invalid rows
    df = df[df['net_debit'] > 0].copy()
    df = df[df['assigned_return'] > 0].copy()

    return df


def get_page_covered_calls(
    df: pd.DataFrame,
    min_annualized: float = 0.10,
    min_downside: float = 0.02,
    earnings_buffer_days: int = 0,
    above_ma20: bool = False,
    above_ma50: bool = False,
    min_volume: int = 0,
) -> pd.DataFrame:
    """Filter and format covered calls for page display.

    Args:
        df: DataFrame with calculated metrics (from calc_covered_calls)
        min_annualized: Minimum annualized return (0.10 = 10%)
        min_downside: Minimum downside protection (0.02 = 2%)
        earnings_buffer_days: Days before expiration to exclude earnings (0 = filter exact)
        above_ma20: Only show stocks above 20-day MA
        above_ma50: Only show stocks above 50-day MA
        min_volume: Minimum option volume
    """
    if df.empty:
        return df

    filtered = df.copy()

    # Min annualized return
    filtered = filtered[filtered['annualized_return'] >= min_annualized]

    # Min downside protection
    filtered = filtered[filtered['downside_protection'] >= min_downside]

    # Volume filter
    if min_volume > 0:
        filtered = filtered[filtered['volume'] >= min_volume]

    # Earnings filter: remove stocks with earnings before expiration + buffer
    if 'days_to_earnings' in filtered.columns:
        filtered = filtered[
            (filtered['days_to_earnings'].isna()) |
            (filtered['days_to_earnings'] <= 0) |
            (filtered['days_to_earnings'] > filtered['DTE'] + earnings_buffer_days)
        ]

    # Technical filters
    if above_ma20 and 'SMA_20' in filtered.columns:
        filtered = filtered[
            (filtered['SMA_20'].isna()) |
            (filtered['stock_price'] >= filtered['SMA_20'])
        ]

    if above_ma50 and 'SMA_50' in filtered.columns:
        filtered = filtered[
            (filtered['SMA_50'].isna()) |
            (filtered['stock_price'] >= filtered['SMA_50'])
        ]

    # Sort by annualized return descending
    filtered = filtered.sort_values('annualized_return', ascending=False)
    filtered.reset_index(drop=True, inplace=True)

    return filtered
