"""
Call Income Simulator Engine.

Simulates monthly covered-call income against an existing protective-put
position.  The user has already bought a long-term put and now wants to
sell short-term calls each month to offset (or exceed) the put cost.

Main entry points
-----------------
- ``simulate_call_income``   – core simulation with aggregated metrics
- ``build_auto_call_plan``   – auto-generate one call per month (X % OTM)
- ``calculate_assignment_scenario`` – what-if for a single month
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

MONTH_MAP = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}


# ── Data classes ────────────────────────────────────────────────────

@dataclass
class MonthlyCall:
    """A single monthly call sale."""
    month_label: str            # e.g. "2026-03 (März)"
    expiration_date: date
    strike: float
    premium: float
    days_to_expiration: int
    open_interest: int


@dataclass
class SimulationResult:
    """Full result of the call-income simulation."""
    # Reference inputs
    symbol: str
    cost_basis: float
    current_price: float
    put_strike: float
    put_price: float
    put_expiration_date: date

    # Call plan
    call_plan: list[MonthlyCall]

    # Aggregated metrics
    total_call_income: float
    net_insurance_cost: float          # put_price - total_call_income
    put_cost_covered_pct: float
    months_to_breakeven: Optional[int]
    effective_cost_basis: float        # cost_basis + put_price - total_call_income
    effective_locked_in_profit: float
    effective_locked_in_profit_pct: float
    avg_monthly_income: float
    avg_monthly_income_pct: float

    # Per-month details (list of dicts)
    monthly_details: list[dict] = field(default_factory=list)


# ── Core simulation ────────────────────────────────────────────────

def simulate_call_income(
    symbol: str,
    cost_basis: float,
    current_price: float,
    put_strike: float,
    put_price: float,
    put_expiration_date: date,
    call_plan: list[MonthlyCall],
) -> SimulationResult:
    """
    Run the full simulation and return aggregated + per-month metrics.

    Parameters
    ----------
    symbol : str
    cost_basis : float – original purchase price per share
    current_price : float – today's stock price
    put_strike : float – strike of the protective put already owned
    put_price : float – price paid for the protective put
    put_expiration_date : date – expiry of the protective put
    call_plan : list[MonthlyCall] – planned monthly call sales

    Returns
    -------
    SimulationResult
    """
    if not call_plan:
        return SimulationResult(
            symbol=symbol,
            cost_basis=cost_basis,
            current_price=current_price,
            put_strike=put_strike,
            put_price=put_price,
            put_expiration_date=put_expiration_date,
            call_plan=[],
            total_call_income=0.0,
            net_insurance_cost=put_price,
            put_cost_covered_pct=0.0,
            months_to_breakeven=None,
            effective_cost_basis=cost_basis + put_price,
            effective_locked_in_profit=put_strike - (cost_basis + put_price),
            effective_locked_in_profit_pct=(
                (put_strike - (cost_basis + put_price)) / (cost_basis + put_price) * 100
                if (cost_basis + put_price) > 0 else 0
            ),
            avg_monthly_income=0.0,
            avg_monthly_income_pct=0.0,
            monthly_details=[],
        )

    total_call_income = sum(c.premium for c in call_plan)
    net_insurance_cost = put_price - total_call_income
    put_cost_covered_pct = (total_call_income / put_price * 100) if put_price > 0 else 0.0
    months_to_breakeven = calculate_months_to_breakeven(put_price, call_plan)
    effective_cost_basis = cost_basis + put_price - total_call_income
    effective_locked_in_profit = put_strike - effective_cost_basis
    effective_locked_in_profit_pct = (
        (effective_locked_in_profit / effective_cost_basis * 100)
        if effective_cost_basis > 0 else 0.0
    )
    num_months = len(call_plan)
    avg_monthly_income = total_call_income / num_months
    avg_monthly_income_pct = (avg_monthly_income / current_price * 100) if current_price > 0 else 0.0

    # Build per-month detail rows
    monthly_details: list[dict] = []
    cumulative = 0.0
    breakeven_found = False
    for call in call_plan:
        cumulative += call.premium
        is_be = cumulative >= put_price and not breakeven_found
        if is_be:
            breakeven_found = True

        assignment_buffer_pct = (
            ((call.strike - current_price) / current_price * 100) if current_price > 0 else 0.0
        )
        call_premium_annualized_pct = (
            (call.premium / current_price) * (365 / call.days_to_expiration) * 100
            if current_price > 0 and call.days_to_expiration > 0 else 0.0
        )

        monthly_details.append({
            "month_label": call.month_label,
            "expiration_date": call.expiration_date,
            "strike": call.strike,
            "premium": call.premium,
            "cumulative": cumulative,
            "put_covered_pct": (cumulative / put_price * 100) if put_price > 0 else 0.0,
            "assignment_buffer_pct": assignment_buffer_pct,
            "status": _get_month_status(cumulative, put_price, is_be),
            "days_to_expiration": call.days_to_expiration,
            "open_interest": call.open_interest,
            "call_premium_annualized_pct": call_premium_annualized_pct,
        })

    return SimulationResult(
        symbol=symbol,
        cost_basis=cost_basis,
        current_price=current_price,
        put_strike=put_strike,
        put_price=put_price,
        put_expiration_date=put_expiration_date,
        call_plan=call_plan,
        total_call_income=total_call_income,
        net_insurance_cost=net_insurance_cost,
        put_cost_covered_pct=put_cost_covered_pct,
        months_to_breakeven=months_to_breakeven,
        effective_cost_basis=effective_cost_basis,
        effective_locked_in_profit=effective_locked_in_profit,
        effective_locked_in_profit_pct=effective_locked_in_profit_pct,
        avg_monthly_income=avg_monthly_income,
        avg_monthly_income_pct=avg_monthly_income_pct,
        monthly_details=monthly_details,
    )


# ── Breakeven helper ───────────────────────────────────────────────

def calculate_months_to_breakeven(
    put_price: float,
    call_plan: list[MonthlyCall],
) -> Optional[int]:
    """Return 1-indexed month number when cumulative premiums >= put_price."""
    cumulative = 0.0
    for i, call in enumerate(call_plan):
        cumulative += call.premium
        if cumulative >= put_price:
            return i + 1
    return None


# ── Auto plan builder ──────────────────────────────────────────────

def find_otm_call_strike(
    available_strikes: list[float],
    current_price: float,
    otm_pct: float,
) -> Optional[float]:
    """
    Find the nearest available strike that is at least *otm_pct* %
    above *current_price*.  Falls back to the highest strike.
    """
    if not available_strikes:
        return None
    target = current_price * (1 + otm_pct / 100)
    candidates = [s for s in available_strikes if s >= target]
    if candidates:
        return min(candidates)
    return max(available_strikes)


def build_auto_call_plan(
    current_price: float,
    put_expiration_date: date,
    otm_pct: float,
    calls_df: pd.DataFrame,
) -> list[MonthlyCall]:
    """
    Auto-generate one call per expiration month up to *put_expiration_date*.

    For each calendar month that has call data the function picks the
    *latest* expiration in that month (= standard monthly), finds the
    nearest OTM strike, and returns a sorted list of ``MonthlyCall``.

    Parameters
    ----------
    current_price : float
    put_expiration_date : date – calls expiring on/after this are excluded
    otm_pct : float – e.g. 10.0 for "10 % OTM"
    calls_df : DataFrame with columns
        ``strike_price, option_price, expiration_date,
          days_to_expiration, open_interest``
    """
    if calls_df is None or calls_df.empty:
        return []

    df = calls_df.copy()
    df["expiration_date"] = pd.to_datetime(df["expiration_date"]).dt.date

    # Only expirations strictly before the put expiry
    df = df[df["expiration_date"] < put_expiration_date]
    if df.empty:
        return []

    df["year_month"] = df["expiration_date"].apply(lambda d: f"{d.year}-{d.month:02d}")

    plan: list[MonthlyCall] = []
    for _ym, group in df.groupby("year_month"):
        # Use the latest (= standard monthly) expiration in that month
        latest_exp = group["expiration_date"].max()
        month_calls = group[group["expiration_date"] == latest_exp]

        strikes = sorted(month_calls["strike_price"].unique())
        target_strike = find_otm_call_strike(strikes, current_price, otm_pct)
        if target_strike is None:
            continue

        row = month_calls[month_calls["strike_price"] == target_strike].iloc[0]
        label = f"{latest_exp.year}-{latest_exp.month:02d} ({MONTH_MAP.get(latest_exp.month, '')})"

        plan.append(MonthlyCall(
            month_label=label,
            expiration_date=latest_exp,
            strike=float(row["strike_price"]),
            premium=float(row["option_price"]),
            days_to_expiration=int(row["days_to_expiration"]),
            open_interest=int(row["open_interest"]),
        ))

    plan.sort(key=lambda c: c.expiration_date)
    return plan


# ── Assignment scenario ────────────────────────────────────────────

def calculate_assignment_scenario(
    call: MonthlyCall,
    cost_basis: float,
    put_price: float,
    put_strike: float,
    cumulative_premiums_before: float,
) -> dict:
    """
    Calculate the financial outcome if the stock is called away at
    *call.strike* in this month.

    Returns a dict with keys:
        sale_price, total_cost, call_credits_so_far,
        profit_if_assigned, put_residual_value,
        total_return, total_return_pct
    """
    total_cost = cost_basis + put_price
    call_credits = cumulative_premiums_before + call.premium
    profit_if_assigned = call.strike - total_cost + call_credits
    put_residual_value = max(0.0, put_strike - call.strike)
    total_return = profit_if_assigned + put_residual_value
    total_return_pct = (total_return / total_cost * 100) if total_cost > 0 else 0.0

    return {
        "sale_price": call.strike,
        "total_cost": total_cost,
        "call_credits_so_far": call_credits,
        "profit_if_assigned": profit_if_assigned,
        "put_residual_value": put_residual_value,
        "total_return": total_return,
        "total_return_pct": total_return_pct,
    }


# ── Private helpers ────────────────────────────────────────────────

def _get_month_status(cumulative: float, put_price: float, is_breakeven_month: bool) -> str:
    if is_breakeven_month:
        return "✅ Breakeven!"
    elif cumulative >= put_price:
        return "💰 Profit"
    else:
        return "⏳ Offen"
