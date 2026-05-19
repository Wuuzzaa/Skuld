"""Zahltagstrategie Dividend Screener - Scoring & Filtering Module.

Implements Nils Gajovi's 11-point matrix:
- 5 Fundamental criteria (PE, margins, EPS growth, D/E, ROE)
- 5 Dividend criteria (yield, growth years, payout ratio, growth rate, classification)
- 1 Technical criterion (price vs SMA200 + RSI + MACD combined)

Scoring: 1-3 points per criterion, max 33 points total.
- >= 23 points: BUY (Kaufen/Aufstocken)
- 12-22 points: WATCH (Beobachten)
- < 12 points: DISCARD (Papierkorb)
"""

import pandas as pd
import numpy as np


def score_pe_ratio(pe: float) -> int:
    """Score trailing P/E ratio. Lower is better for value."""
    if pd.isna(pe) or pe <= 0:
        return 1
    if pe <= 15:
        return 3
    if pe <= 25:
        return 2
    return 1


def score_profit_margin(margin_pct: float) -> int:
    """Score profit margin %. Higher is better."""
    if pd.isna(margin_pct):
        return 1
    if margin_pct >= 20:
        return 3
    if margin_pct >= 10:
        return 2
    return 1


def score_eps_growth(growth_pct: float) -> int:
    """Score forward EPS growth %. Higher is better."""
    if pd.isna(growth_pct):
        return 1
    if growth_pct >= 15:
        return 3
    if growth_pct >= 5:
        return 2
    return 1


def score_debt_to_equity(de: float) -> int:
    """Score Debt/Equity ratio. Lower is better (less leveraged)."""
    if pd.isna(de):
        return 1
    if de <= 50:
        return 3
    if de <= 150:
        return 2
    return 1


def score_roe(roe_pct: float) -> int:
    """Score Return on Equity %. Higher is better."""
    if pd.isna(roe_pct):
        return 1
    if roe_pct >= 20:
        return 3
    if roe_pct >= 10:
        return 2
    return 1


def score_dividend_yield(yield_pct: float) -> int:
    """Score dividend yield %. Sweet spot 3-6%, very high might be risky."""
    if pd.isna(yield_pct) or yield_pct <= 0:
        return 1
    if 3.0 <= yield_pct <= 8.0:
        return 3
    if 2.0 <= yield_pct < 3.0 or 8.0 < yield_pct <= 10.0:
        return 2
    return 1


def score_dividend_growth_years(years: float) -> int:
    """Score consecutive dividend growth years. More is better."""
    if pd.isna(years) or years < 1:
        return 1
    if years >= 25:  # Champion
        return 3
    if years >= 10:  # Contender
        return 2
    return 1


def score_payout_ratio(payout_pct: float) -> int:
    """Score payout ratio %. Sustainable range is 30-75%."""
    if pd.isna(payout_pct) or payout_pct <= 0:
        return 1
    if 20 <= payout_pct <= 60:
        return 3
    if 60 < payout_pct <= 80:
        return 2
    return 1


def score_dividend_growth_rate(five_year_avg: float, current_yield: float) -> int:
    """Score implied dividend growth via 5yr avg vs current yield.
    If current yield is much higher than 5yr avg, stock has fallen (opportunity).
    We approximate DGR from the gap between current and historical yield.
    """
    if pd.isna(five_year_avg) or pd.isna(current_yield) or five_year_avg <= 0:
        return 1
    # Higher current yield vs 5yr avg = stock is undervalued or div was raised
    ratio = current_yield / five_year_avg
    if ratio >= 1.3:
        return 3
    if ratio >= 1.0:
        return 2
    return 1


def score_dividend_classification(classification: str) -> int:
    """Score by dividend champion/contender/challenger classification."""
    if pd.isna(classification):
        return 1
    c = str(classification).lower()
    if 'champion' in c:
        return 3
    if 'contender' in c:
        return 2
    if 'challenger' in c:
        return 2
    return 1


def score_technical(pct_from_sma200: float, rsi: float, macd_hist: float) -> int:
    """Combined technical score: price vs SMA200, RSI, MACD.
    Looking for oversold/undervalued (below SMA200, low RSI, MACD turning up).
    """
    points = 0

    # Price below SMA200 = potential value (Nils likes buying below average)
    if not pd.isna(pct_from_sma200):
        if pct_from_sma200 < -10:
            points += 1.5
        elif pct_from_sma200 < 0:
            points += 1.0

    # RSI < 40 = oversold, RSI > 70 = overbought
    if not pd.isna(rsi):
        if rsi < 40:
            points += 1.0
        elif rsi < 55:
            points += 0.5

    # MACD histogram turning positive = momentum shifting up
    if not pd.isna(macd_hist):
        if macd_hist > 0:
            points += 0.5

    # Convert to 1-3 scale
    if points >= 2.0:
        return 3
    if points >= 1.0:
        return 2
    return 1


def calculate_dividend_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the 11-point scoring matrix to each stock.

    Returns DataFrame with individual scores, total score, and recommendation.
    """
    if df.empty:
        return df

    result = df.copy()

    # Fundamental scores (5 criteria)
    result['score_pe'] = result['trailing_pe'].apply(score_pe_ratio)
    result['score_margin'] = result['profit_margin_pct'].apply(score_profit_margin)
    result['score_eps_growth'] = result['eps_growth_pct'].apply(score_eps_growth)
    result['score_debt'] = result['debt_to_equity'].apply(score_debt_to_equity)
    result['score_roe'] = result['roe_pct'].apply(score_roe)

    # Dividend scores (5 criteria)
    result['score_yield'] = result['dividend_yield_pct'].apply(score_dividend_yield)
    result['score_div_years'] = result['dividend_growth_years'].apply(score_dividend_growth_years)
    result['score_payout'] = result['payout_ratio_pct'].apply(score_payout_ratio)
    result['score_div_growth'] = result.apply(
        lambda r: score_dividend_growth_rate(r['five_year_avg_yield'], r['dividend_yield_pct']),
        axis=1
    )
    result['score_classification'] = result['dividend_classification'].apply(score_dividend_classification)

    # Technical score (1 criterion)
    result['score_technical'] = result.apply(
        lambda r: score_technical(r['pct_from_sma200'], r['rsi_14'], r['macd_histogram']),
        axis=1
    )

    # Sub-totals
    result['score_fundamental'] = (
        result['score_pe'] + result['score_margin'] + result['score_eps_growth'] +
        result['score_debt'] + result['score_roe']
    )
    result['score_dividend'] = (
        result['score_yield'] + result['score_div_years'] + result['score_payout'] +
        result['score_div_growth'] + result['score_classification']
    )
    result['score_total'] = result['score_fundamental'] + result['score_dividend'] + result['score_technical']

    # Recommendation
    result['recommendation'] = result['score_total'].apply(
        lambda s: 'BUY' if s >= 23 else ('WATCH' if s >= 12 else 'DISCARD')
    )

    return result


def filter_dividend_screener(
    df: pd.DataFrame,
    min_yield: float = 3.0,
    max_yield: float = 100.0,
    min_price: float = 10.0,
    max_price: float = 10000.0,
    min_market_cap_b: float = 0.0,
    min_avg_volume: int = 0,
    max_debt_to_equity: float = 0.0,
    min_dividend_years: int = 0,
    min_score: int = 0,
    sector: str = '',
    below_sma200: bool = False,
    above_52w_low: bool = False,
    only_champions: bool = False,
    only_contenders_plus: bool = False,
    exclude_reits: bool = False,
) -> pd.DataFrame:
    """Apply Nils-style screening filters.

    Returns filtered DataFrame ready for scoring.
    """
    if df.empty:
        return df

    filtered = df.copy()

    # Price filter
    if min_price > 0:
        filtered = filtered[filtered['price'] >= min_price]
    if max_price < 10000:
        filtered = filtered[filtered['price'] <= max_price]

    # Yield filter
    if min_yield > 0:
        filtered = filtered[filtered['dividend_yield_pct'] >= min_yield]
    if max_yield < 100:
        filtered = filtered[filtered['dividend_yield_pct'] <= max_yield]

    # Market cap
    if min_market_cap_b > 0:
        filtered = filtered[filtered['market_cap_b'] >= min_market_cap_b]

    # Volume
    if min_avg_volume > 0:
        filtered = filtered[filtered['avg_volume'] >= min_avg_volume]

    # Debt/Equity
    if max_debt_to_equity > 0:
        filtered = filtered[
            (filtered['debt_to_equity'].isna()) |
            (filtered['debt_to_equity'] <= max_debt_to_equity)
        ]

    # Dividend growth years
    if min_dividend_years > 0:
        filtered = filtered[filtered['dividend_growth_years'] >= min_dividend_years]

    # Sector
    if sector:
        filtered = filtered[filtered['sector'] == sector]

    # Technical: below SMA200
    if below_sma200:
        filtered = filtered[
            (filtered['pct_from_sma200'].notna()) &
            (filtered['pct_from_sma200'] < 0)
        ]

    # Above 52-week low (not in free-fall)
    if above_52w_low:
        filtered = filtered[
            (filtered['week_52_low'].notna()) &
            (filtered['price'] > filtered['week_52_low'] * 1.1)
        ]

    # Classification filter
    if only_champions:
        filtered = filtered[filtered['dividend_classification'] == 'Dividend Champion']
    elif only_contenders_plus:
        filtered = filtered[filtered['dividend_classification'].isin(
            ['Dividend Champion', 'Dividend Contender']
        )]

    # Exclude REITs (they have different fundamentals)
    if exclude_reits:
        filtered = filtered[filtered['sector'] != 'Real Estate']

    # Score filter
    if min_score > 0:
        filtered = filtered[filtered['score_total'] >= min_score]

    return filtered.sort_values('score_total', ascending=False).reset_index(drop=True)
