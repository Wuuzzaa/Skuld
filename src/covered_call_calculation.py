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
    if above_ma20 and '20_day_MA' in filtered.columns:
        filtered = filtered[
            (filtered['20_day_MA'].isna()) |
            (filtered['stock_price'] >= filtered['20_day_MA'])
        ]

    if above_ma50 and '50_day_MA' in filtered.columns:
        filtered = filtered[
            (filtered['50_day_MA'].isna()) |
            (filtered['stock_price'] >= filtered['50_day_MA'])
        ]

    # Sort by annualized return descending
    filtered = filtered.sort_values('annualized_return', ascending=False)
    filtered.reset_index(drop=True, inplace=True)

    # Format percentage columns for display (multiply by 100)
    filtered['assigned_return_pct'] = filtered['assigned_return'] * 100
    filtered['annualized_return_pct'] = filtered['annualized_return'] * 100
    filtered['downside_protection_pct'] = filtered['downside_protection'] * 100
    filtered['moneyness_pct'] = filtered['moneyness'] * 100

    # Select and rename columns for display
    display_cols = [
        'symbol', 'company_name', 'stock_price', 'strike_price', 'premium',
        'net_debit', 'assigned_return_pct', 'annualized_return_pct',
        'downside_protection_pct', 'moneyness_pct', 'DTE', 'delta', 'iv',
        'open_interest', 'volume', 'iv_rank', 'iv_percentile',
        'earnings_date_next', 'days_to_earnings',
        'company_sector', '20_day_MA', '50_day_MA',
    ]

    # Only include columns that exist
    available = [c for c in display_cols if c in filtered.columns]
    result = filtered[available].copy()

    # Rename for cleaner display
    rename_map = {
        'company_name': 'Company',
        'stock_price': 'Stock',
        'strike_price': 'Strike',
        'premium': 'Premium',
        'net_debit': 'Net Debit',
        'assigned_return_pct': 'Assigned %',
        'annualized_return_pct': 'Annual %',
        'downside_protection_pct': 'Protection %',
        'moneyness_pct': 'ITM %',
        'open_interest': 'OI',
        'volume': 'Vol',
    }
    result.rename(columns=rename_map, inplace=True)

    return result
