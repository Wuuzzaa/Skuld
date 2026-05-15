"""Covered Call Screener - PowerOptions-style calculations.

Calculates: Net Debit, Assigned Return, Annualized Return, Downside Protection.
Filters: Earnings avoidance, technical indicators, liquidity, PowerOptions criteria.

PowerOptions Filtering Criteria (from YouTube transcripts):
- MACD above signal line, both positive (momentum confirmation)
- RSI < 70 (not overbought)
- EPS Growth > 5% (fundamental quality)
- P/E Ratio 0-50 (valuation sanity check)
- Analyst Recommendation < 2.6 (1=Strong Buy, 5=Sell)
- Avg Volume > 500k (institutional liquidity)
- Market Cap > 2500M (no micro-caps)
- No Biotech (too volatile for covered calls)
- No Leveraged ETFs (decay risk)
- IV/HV Ratio consideration (fair premium vs risk)
"""

import pandas as pd
import numpy as np
import logging
import os

logger = logging.getLogger(os.path.basename(__file__))

# Industries/sectors to exclude (too volatile for covered calls)
EXCLUDED_INDUSTRIES = [
    'biotechnology',
    'drug manufacturers',
]

# Leveraged/Inverse ETF keywords to exclude
LEVERAGED_ETF_KEYWORDS = [
    '2x', '3x', '-2x', '-3x', 'ultra', 'direxion', 'proshares ultra',
    'leveraged', 'inverse',
]


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

    # Investment & profit per contract (100 shares)
    df['investment'] = df['stock_price'] * 100
    df['premium_income'] = df['premium'] * 100
    df['net_cost'] = df['net_debit'] * 100
    df['max_profit'] = (df['strike_price'] - df['stock_price'] + df['premium']) * 100

    # IV/HV Ratio (implied vs historical volatility)
    if 'hv_30d' in df.columns and 'iv' in df.columns:
        df['iv_hv_ratio'] = np.where(
            (df['hv_30d'] > 0) & df['hv_30d'].notna(),
            df['iv'] / df['hv_30d'],
            np.nan
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
    # PowerOptions filters
    macd_positive: bool = False,
    rsi_below_70: bool = False,
    min_eps_growth: float = None,
    max_pe_ratio: float = None,
    max_recommendation: float = None,
    min_avg_volume: int = None,
    min_market_cap: float = None,
    exclude_biotech: bool = False,
    exclude_leveraged: bool = False,
    max_iv_hv_ratio: float = None,
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
        macd_positive: MACD above signal line, both positive
        rsi_below_70: RSI must be below 70 (not overbought)
        min_eps_growth: Minimum EPS growth % (e.g., 5.0 for >5%)
        max_pe_ratio: Maximum P/E ratio (e.g., 50.0)
        max_recommendation: Maximum analyst recommendation (e.g., 2.6)
        min_avg_volume: Minimum average daily volume (e.g., 500000)
        min_market_cap: Minimum market cap in millions (e.g., 2500)
        exclude_biotech: Exclude biotech/drug manufacturers
        exclude_leveraged: Exclude leveraged/inverse ETFs
        max_iv_hv_ratio: Maximum IV/HV ratio (premium fairness check)
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

    # === PowerOptions Filters ===

    # MACD: above signal line AND both positive (bullish momentum)
    if macd_positive and 'macd' in filtered.columns and 'macd_signal' in filtered.columns:
        filtered = filtered[
            (filtered['macd'].isna()) |
            (
                (filtered['macd'] > filtered['macd_signal']) &
                (filtered['macd'] > 0) &
                (filtered['macd_signal'] > 0)
            )
        ]

    # RSI below 70 (not overbought)
    if rsi_below_70 and 'rsi_14' in filtered.columns:
        filtered = filtered[
            (filtered['rsi_14'].isna()) |
            (filtered['rsi_14'] < 70)
        ]

    # EPS Growth filter
    if min_eps_growth is not None and 'eps_growth' in filtered.columns:
        filtered = filtered[
            (filtered['eps_growth'].isna()) |
            (filtered['eps_growth'] >= min_eps_growth)
        ]

    # P/E Ratio filter (0 < P/E < max)
    if max_pe_ratio is not None and 'pe_ratio' in filtered.columns:
        filtered = filtered[
            (filtered['pe_ratio'].isna()) |
            ((filtered['pe_ratio'] > 0) & (filtered['pe_ratio'] <= max_pe_ratio))
        ]

    # Analyst Recommendation (lower = more bullish, 1=Strong Buy to 5=Sell)
    if max_recommendation is not None and 'analyst_recommendation' in filtered.columns:
        filtered = filtered[
            (filtered['analyst_recommendation'].isna()) |
            (filtered['analyst_recommendation'] <= max_recommendation)
        ]

    # Average Volume (institutional liquidity)
    if min_avg_volume is not None and 'avg_volume' in filtered.columns:
        filtered = filtered[
            (filtered['avg_volume'].isna()) |
            (filtered['avg_volume'] >= min_avg_volume)
        ]

    # Market Cap filter (in millions)
    if min_market_cap is not None and 'market_cap' in filtered.columns:
        filtered = filtered[
            (filtered['market_cap'].isna()) |
            (filtered['market_cap'] >= min_market_cap * 1_000_000)
        ]

    # Exclude Biotech/Drug Manufacturers
    if exclude_biotech and 'company_industry' in filtered.columns:
        filtered = filtered[
            (filtered['company_industry'].isna()) |
            (~filtered['company_industry'].str.lower().isin(EXCLUDED_INDUSTRIES))
        ]

    # Exclude Leveraged/Inverse ETFs (check company_name)
    if exclude_leveraged and 'company_name' in filtered.columns:
        mask = filtered['company_name'].str.lower().fillna('')
        for keyword in LEVERAGED_ETF_KEYWORDS:
            mask_hit = mask.str.contains(keyword, na=False)
            filtered = filtered[~mask_hit]

    # IV/HV Ratio (premium fairness — too high means overpriced risk)
    if max_iv_hv_ratio is not None and 'iv_hv_ratio' in filtered.columns:
        filtered = filtered[
            (filtered['iv_hv_ratio'].isna()) |
            (filtered['iv_hv_ratio'] <= max_iv_hv_ratio)
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
        'symbol', 'company_name', 'company_sector', 'company_industry',
        'expiration_date',
        'stock_price', 'strike_price', 'premium',
        'net_debit', 'investment', 'premium_income', 'net_cost', 'max_profit',
        'assigned_return_pct', 'annualized_return_pct',
        'downside_protection_pct', 'moneyness_pct', 'DTE', 'delta', 'iv',
        'open_interest', 'volume', 'iv_rank', 'iv_percentile',
        'earnings_date_next', 'days_to_earnings',
        'SMA_20', 'SMA_50',
        'macd', 'macd_signal', 'rsi_14',
        'eps_growth', 'pe_ratio', 'analyst_recommendation',
        'avg_volume', 'market_cap', 'iv_hv_ratio',
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
        'investment': 'Investment',
        'premium_income': 'Prem Income',
        'net_cost': 'Net Cost',
        'max_profit': 'Max Profit',
        'assigned_return_pct': 'Assigned %',
        'annualized_return_pct': 'Annual %',
        'downside_protection_pct': 'Protection %',
        'moneyness_pct': 'ITM %',
        'open_interest': 'OI',
        'volume': 'Vol',
        'macd': 'MACD',
        'macd_signal': 'MACD Signal',
        'rsi_14': 'RSI',
        'eps_growth': 'EPS Growth %',
        'pe_ratio': 'P/E',
        'analyst_recommendation': 'Rec',
        'avg_volume': 'Avg Vol',
        'market_cap': 'Mkt Cap',
        'iv_hv_ratio': 'IV/HV',
    }
    result.rename(columns=rename_map, inplace=True)

    # Format dollar columns for table readability
    for col in ['Stock', 'Strike', 'Premium', 'Net Debit']:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: f"${x:.2f}" if pd.notnull(x) else ""
            )
    for col in ['Investment', 'Prem Income', 'Net Cost', 'Max Profit']:
        if col in result.columns:
            result[col] = result[col].apply(
                lambda x: f"${x:,.0f}" if pd.notnull(x) else ""
            )

    # Format large numbers for table readability (string columns)
    # These are display-only — detail panel should use raw values before rename
    if 'Mkt Cap' in result.columns:
        result['Mkt Cap'] = result['Mkt Cap'].apply(
            lambda x: f"${x/1e9:.1f}B" if pd.notnull(x) and x >= 1e9
            else (f"${x/1e6:.0f}M" if pd.notnull(x) and x > 0 else "")
        )
    if 'Avg Vol' in result.columns:
        result['Avg Vol'] = result['Avg Vol'].apply(
            lambda x: f"{x/1e6:.1f}M" if pd.notnull(x) and x >= 1e6
            else (f"{x/1e3:.0f}K" if pd.notnull(x) and x > 0 else "")
        )
    if 'OI' in result.columns:
        result['OI'] = result['OI'].apply(
            lambda x: f"{int(x):,}" if pd.notnull(x) else ""
        )
    if 'Vol' in result.columns:
        result['Vol'] = result['Vol'].apply(
            lambda x: f"{int(x):,}" if pd.notnull(x) else ""
        )

    return result
