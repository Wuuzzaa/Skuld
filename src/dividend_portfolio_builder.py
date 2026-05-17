"""Dividend Portfolio Builder - Optimized portfolio allocation for target monthly income.

Given a target monthly dividend (e.g. 100 EUR), builds an optimized portfolio from
scored dividend stocks that:
1. Achieves the target annual dividend income
2. Spreads payments across all 12 months (3 quarterly cycles)
3. Diversifies across sectors (max 2 per sector)
4. Prioritizes highest-scored stocks from the 11-point matrix
5. Calculates exact shares and investment needed per position
"""

import pandas as pd
import numpy as np
from typing import Optional


# EUR/USD exchange rate (can be overridden)
DEFAULT_EUR_USD = 1.08


def build_dividend_portfolio(
    candidates_df: pd.DataFrame,
    target_monthly_eur: float = 100.0,
    eur_usd_rate: float = DEFAULT_EUR_USD,
    max_positions: int = 20,
    max_per_sector: int = 2,
    min_score: int = 18,
    min_yield_pct: float = 2.5,
    min_price: float = 10.0,
    max_single_position_pct: float = 10.0,
) -> dict:
    """Build an optimized dividend portfolio to achieve target monthly income.

    Args:
        candidates_df: DataFrame from dividend_portfolio_builder.sql + scoring
        target_monthly_eur: Target monthly dividend in EUR
        eur_usd_rate: EUR/USD exchange rate
        max_positions: Maximum number of stocks in portfolio
        max_per_sector: Maximum stocks per sector
        min_score: Minimum score threshold for candidates
        min_yield_pct: Minimum dividend yield %
        min_price: Minimum stock price
        max_single_position_pct: Max % of total investment in one stock

    Returns:
        Dict with portfolio positions, summary stats, and monthly breakdown
    """
    target_annual_eur = target_monthly_eur * 12
    target_annual_usd = target_annual_eur * eur_usd_rate

    # Filter candidates
    df = candidates_df.copy()
    df = df[df['score_total'] >= min_score]
    df = df[df['dividend_yield_pct'] >= min_yield_pct]
    df = df[df['price'] >= min_price]
    df = df[df['annual_dividend_rate'] > 0]

    if df.empty:
        return _empty_result(target_monthly_eur, target_annual_usd)

    # Sort by score (primary) then yield (secondary)
    df = df.sort_values(['score_total', 'dividend_yield_pct'], ascending=[False, False])

    # Split into payment cycles
    cycle_a = df[df['payment_cycle'].isin(['A', 'MONTHLY'])].copy()
    cycle_b = df[df['payment_cycle'].isin(['B', 'MONTHLY'])].copy()
    cycle_c = df[df['payment_cycle'].isin(['C', 'MONTHLY'])].copy()

    # Target per cycle (1/3 each)
    target_per_cycle_usd = target_annual_usd / 3.0
    positions_per_cycle = max(3, max_positions // 3)

    # Allocate stocks per cycle using greedy approach
    portfolio = []
    sector_counts = {}

    for cycle_name, cycle_df, cycle_months in [
        ('A', cycle_a, 'Jan/Apr/Jul/Oct'),
        ('B', cycle_b, 'Feb/May/Aug/Nov'),
        ('C', cycle_c, 'Mar/Jun/Sep/Dec'),
    ]:
        cycle_positions = _allocate_cycle(
            cycle_df=cycle_df,
            target_dividend_usd=target_per_cycle_usd,
            max_positions=positions_per_cycle,
            max_per_sector=max_per_sector,
            sector_counts=sector_counts,
            cycle_name=cycle_name,
            cycle_months=cycle_months,
            already_selected=[p['symbol'] for p in portfolio],
        )
        portfolio.extend(cycle_positions)

    if not portfolio:
        return _empty_result(target_monthly_eur, target_annual_usd)

    # Calculate totals
    total_investment = sum(p['investment_usd'] for p in portfolio)
    total_annual_dividend = sum(p['annual_dividend_usd'] for p in portfolio)
    achieved_monthly_eur = (total_annual_dividend / eur_usd_rate) / 12.0

    # Apply max_single_position_pct constraint
    if total_investment > 0:
        max_position_usd = total_investment * (max_single_position_pct / 100.0)
        for p in portfolio:
            if p['investment_usd'] > max_position_usd:
                # Cap position and recalculate shares
                ratio = max_position_usd / p['investment_usd']
                p['shares'] = max(1, int(p['shares'] * ratio))
                p['investment_usd'] = round(p['shares'] * p['price'], 2)
                p['annual_dividend_usd'] = round(p['shares'] * p['annual_dividend_rate'], 2)

        # Recalculate totals after capping
        total_investment = sum(p['investment_usd'] for p in portfolio)
        total_annual_dividend = sum(p['annual_dividend_usd'] for p in portfolio)
        achieved_monthly_eur = (total_annual_dividend / eur_usd_rate) / 12.0

    # Add weight % to each position
    for p in portfolio:
        p['weight_pct'] = round((p['investment_usd'] / total_investment) * 100, 1) if total_investment > 0 else 0

    # Monthly breakdown
    monthly_breakdown = _calculate_monthly_breakdown(portfolio, eur_usd_rate)

    # Summary
    summary = {
        'target_monthly_eur': target_monthly_eur,
        'target_annual_eur': target_annual_eur,
        'achieved_monthly_eur': round(achieved_monthly_eur, 2),
        'achieved_annual_eur': round(achieved_monthly_eur * 12, 2),
        'target_coverage_pct': round((achieved_monthly_eur / target_monthly_eur) * 100, 1) if target_monthly_eur > 0 else 0,
        'total_investment_usd': round(total_investment, 2),
        'total_investment_eur': round(total_investment / eur_usd_rate, 2),
        'total_annual_dividend_usd': round(total_annual_dividend, 2),
        'portfolio_yield_pct': round((total_annual_dividend / total_investment) * 100, 2) if total_investment > 0 else 0,
        'num_positions': len(portfolio),
        'num_sectors': len(set(p['sector'] for p in portfolio)),
        'avg_score': round(np.mean([p['score_total'] for p in portfolio]), 1),
        'avg_dividend_years': round(np.mean([p['dividend_growth_years'] for p in portfolio if p['dividend_growth_years'] and p['dividend_growth_years'] > 0]), 0),
        'eur_usd_rate': eur_usd_rate,
    }

    return {
        'portfolio': sorted(portfolio, key=lambda p: p['score_total'], reverse=True),
        'summary': summary,
        'monthly_breakdown': monthly_breakdown,
    }


def _allocate_cycle(
    cycle_df: pd.DataFrame,
    target_dividend_usd: float,
    max_positions: int,
    max_per_sector: int,
    sector_counts: dict,
    cycle_name: str,
    cycle_months: str,
    already_selected: list,
) -> list:
    """Greedily allocate stocks for one payment cycle."""
    positions = []
    remaining_target = target_dividend_usd
    used_in_cycle = 0

    for _, row in cycle_df.iterrows():
        if used_in_cycle >= max_positions:
            break
        if remaining_target <= 0:
            break
        if row['symbol'] in already_selected:
            continue

        sector = row['sector']
        if sector_counts.get(sector, 0) >= max_per_sector:
            continue

        # Calculate how many shares needed for equal allocation
        # Each stock should contribute roughly equally within cycle
        target_per_stock = remaining_target / max(1, max_positions - used_in_cycle)
        # But cap at what this stock can contribute per $ invested
        annual_div_per_share = row['annual_dividend_rate']
        if annual_div_per_share <= 0:
            continue

        shares_needed = max(1, int(np.ceil(target_per_stock / annual_div_per_share)))
        investment = shares_needed * row['price']
        annual_div = shares_needed * annual_div_per_share

        position = {
            'symbol': row['symbol'],
            'company_name': row['company_name'],
            'sector': sector,
            'industry': row.get('industry', ''),
            'price': float(row['price']),
            'shares': int(shares_needed),
            'investment_usd': round(float(investment), 2),
            'annual_dividend_rate': float(annual_div_per_share),
            'annual_dividend_usd': round(float(annual_div), 2),
            'quarterly_dividend_usd': round(float(annual_div) / 4, 2),
            'dividend_yield_pct': float(row['dividend_yield_pct']),
            'dividend_growth_years': int(row['dividend_growth_years']) if pd.notna(row['dividend_growth_years']) else 0,
            'dividend_classification': row.get('dividend_classification', 'None'),
            'score_total': int(row['score_total']),
            'payment_cycle': cycle_name,
            'payment_months': cycle_months,
        }

        positions.append(position)
        sector_counts[sector] = sector_counts.get(sector, 0) + 1
        already_selected.append(row['symbol'])
        remaining_target -= annual_div
        used_in_cycle += 1

    return positions


def _calculate_monthly_breakdown(portfolio: list, eur_usd_rate: float) -> list:
    """Calculate expected dividend income per month."""
    months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
    ]
    cycle_months_map = {
        'A': [0, 3, 6, 9],   # Jan, Apr, Jul, Oct
        'B': [1, 4, 7, 10],  # Feb, May, Aug, Nov
        'C': [2, 5, 8, 11],  # Mar, Jun, Sep, Dec
        'MONTHLY': list(range(12)),
    }

    monthly = [0.0] * 12
    for p in portfolio:
        cycle = p['payment_cycle']
        pay_months = cycle_months_map.get(cycle, [])
        if pay_months:
            per_payment = p['annual_dividend_usd'] / len(pay_months)
            for m in pay_months:
                monthly[m] += per_payment

    return [
        {
            'month': months[i],
            'dividend_usd': round(monthly[i], 2),
            'dividend_eur': round(monthly[i] / eur_usd_rate, 2),
        }
        for i in range(12)
    ]


def _empty_result(target_monthly_eur: float, target_annual_usd: float) -> dict:
    """Return empty result when no portfolio can be built."""
    return {
        'portfolio': [],
        'summary': {
            'target_monthly_eur': target_monthly_eur,
            'target_annual_eur': target_monthly_eur * 12,
            'achieved_monthly_eur': 0,
            'achieved_annual_eur': 0,
            'target_coverage_pct': 0,
            'total_investment_usd': 0,
            'total_investment_eur': 0,
            'total_annual_dividend_usd': 0,
            'portfolio_yield_pct': 0,
            'num_positions': 0,
            'num_sectors': 0,
            'avg_score': 0,
            'avg_dividend_years': 0,
            'eur_usd_rate': DEFAULT_EUR_USD,
        },
        'monthly_breakdown': [{'month': m, 'dividend_usd': 0, 'dividend_eur': 0}
                              for m in ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']],
    }
