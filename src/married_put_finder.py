"""
Married Put Finder – Calculation engine.

Provides PowerOptions-style metrics for the RadioActive Trading method:
  • Put-only view  (Buy Put Month selected, Sell Call Month = None)
  • Collar view    (Buy Put Month + Sell Call Month selected)

For collar mode, each put is paired with **every** call whose strike is
≥ the put strike (same-strike collar + wide collar).  When calls span
multiple expiration dates the combinations are multiplied across all
dates, giving the full PowerOptions-style matrix.

Uses ``premium_option_price`` (midpoint) from ``OptionDataMerged`` when
available; falls back to ``option_price`` (day_close) otherwise.
"""

import logging
from datetime import date

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Month display names (German)
MONTH_MAP: dict[int, str] = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}


# ── helpers ─────────────────────────────────────────────────────────

def _midpoint_price(df: pd.DataFrame) -> pd.Series:
    """
    Return the best available price per row.

    Prefer ``premium_option_price`` (true midpoint from the view);
    fall back to ``option_price`` (day_close alias) when the midpoint
    column is missing or NaN.
    """
    if "premium_option_price" in df.columns:
        return df["premium_option_price"].fillna(df["option_price"])
    return df["option_price"]


def _put_label(row: pd.Series) -> str:
    """Build a readable put description like 'TSLA 2024 02-AUG 240.00 PUT (28)'."""
    exp = row["expiration_date"]
    return (
        f"{row['symbol']} {exp.year} "
        f"{exp.strftime('%d-%b').upper()} "
        f"{row['strike_price']:.2f} PUT ({int(row['days_to_expiration'])})"
    )


def _call_label(row: pd.Series) -> str:
    """Build a readable call description like 'TSLA 2024 12-JUL 240.00 CALL (7)'."""
    exp = row["expiration_date"]
    return (
        f"{row['symbol']} {exp.year} "
        f"{exp.strftime('%d-%b').upper()} "
        f"{row['strike_price']:.2f} CALL ({int(row['days_to_expiration'])})"
    )


# ── core functions ──────────────────────────────────────────────────

def calculate_put_only_metrics(
    puts_df: pd.DataFrame,
    cost_basis: float,
    current_price: float,
) -> pd.DataFrame:
    """
    Calculate Put-only Married Put metrics (no Call involved).

    Matches the PowerOptions "Sell Call Month = None" view.

    Uses ``premium_option_price`` (midpoint) when available, otherwise
    ``option_price``.

    Returned columns (appended to a copy of *puts_df*):
        put_label              – e.g. "PG 2025 03-OCT 170.00 PUT (42)"
        put_midpoint_price     – premium_option_price (or option_price fallback)
        put_time_value         – midpoint − max(0, strike − current_price)
        put_time_value_per_mo  – time_value / (DTE / 30)
        new_cost_basis         – cost_basis + midpoint
        locked_in_profit       – strike − new_cost_basis
        locked_in_profit_pct   – locked_in_profit / new_cost_basis × 100
    """
    if puts_df.empty:
        return puts_df

    df = puts_df.copy()
    df["expiration_date"] = pd.to_datetime(df["expiration_date"])

    # Best available price
    midprice = _midpoint_price(df)

    df["put_label"] = df.apply(_put_label, axis=1)
    df["put_midpoint_price"] = midprice

    # Intrinsic & time value
    df["intrinsic_value"] = (df["strike_price"] - current_price).clip(lower=0)
    df["put_time_value"] = midprice - df["intrinsic_value"]

    # Time value per month (30-day basis)
    df["put_time_value_per_mo"] = df.apply(
        lambda r: r["put_time_value"] / (r["days_to_expiration"] / 30)
        if r["days_to_expiration"] > 0 else 0.0,
        axis=1,
    )

    # New cost basis & locked-in profit
    df["new_cost_basis"] = cost_basis + midprice
    df["locked_in_profit"] = df["strike_price"] - df["new_cost_basis"]
    df["locked_in_profit_pct"] = df.apply(
        lambda r: (r["locked_in_profit"] / r["new_cost_basis"] * 100)
        if r["new_cost_basis"] != 0 else 0.0,
        axis=1,
    )

    return df


def calculate_collar_metrics(
    puts_df: pd.DataFrame,
    calls_df: pd.DataFrame,
    cost_basis: float,
    current_price: float,
) -> pd.DataFrame:
    """
    Build the full collar combination matrix and compute metrics.

    For each put, **every** call with ``call_strike >= put_strike`` is
    paired (same-strike collar + wide collar).  When calls span multiple
    expiration dates the combinations are multiplied across all dates —
    exactly like the PowerOptions output.

    Returned columns:
        put_label, put_midpoint_price, intrinsic_value,
        put_time_value, put_time_value_per_mo
            – same as calculate_put_only_metrics
        call_label             – e.g. "TSLA 2024 12-JUL 240.00 CALL (7)"
        call_midpoint_price    – call midpoint price
        new_cost_basis         – cost_basis + put_midpoint − call_midpoint
        locked_in_profit       – put_strike − new_cost_basis
        locked_in_profit_pct   – locked_in_profit / new_cost_basis × 100
        pct_assigned           – (call_strike − NCB) / NCB × 100
        pct_assigned_with_put  – includes residual put value at call strike
    """
    # Start with put-only metrics (one row per put)
    put_metrics = calculate_put_only_metrics(puts_df, cost_basis, current_price)

    if put_metrics.empty:
        return put_metrics

    if calls_df is None or calls_df.empty:
        # No calls → add empty call columns for consistent schema
        for col in ("call_label", "call_midpoint_price", "pct_assigned", "pct_assigned_with_put"):
            put_metrics[col] = None
        return put_metrics

    # Prepare calls with midpoint
    calls = calls_df.copy()
    calls["expiration_date"] = pd.to_datetime(calls["expiration_date"])
    calls["_mid"] = _midpoint_price(calls)

    # Build list of result rows
    rows: list[dict] = []

    for _, put_row in put_metrics.iterrows():
        put_strike = float(put_row["strike_price"])
        put_mid = float(put_row["put_midpoint_price"])

        # All calls with strike >= put strike (same-strike + wide collar)
        valid_calls = calls[calls["strike_price"] >= put_strike]

        if valid_calls.empty:
            # No valid call → put-only row with empty call columns
            row_dict = put_row.to_dict()
            row_dict["call_label"] = None
            row_dict["call_midpoint_price"] = None
            row_dict["pct_assigned"] = None
            row_dict["pct_assigned_with_put"] = None
            rows.append(row_dict)
            continue

        for _, call_row in valid_calls.iterrows():
            cp = float(call_row["_mid"])
            cs = float(call_row["strike_price"])

            ncb = cost_basis + put_mid - cp
            lip = put_strike - ncb
            lip_pct = (lip / ncb * 100) if ncb != 0 else 0.0

            # % Assigned (gain if shares called away at call strike)
            pa = ((cs - ncb) / ncb * 100) if ncb != 0 else 0.0

            # % Assigned with Put (includes residual put value)
            put_residual = max(0.0, put_strike - cs)
            pawp = ((cs - ncb + put_residual) / ncb * 100) if ncb != 0 else 0.0

            row_dict = put_row.to_dict()
            row_dict["call_label"] = _call_label(call_row)
            row_dict["call_midpoint_price"] = cp
            row_dict["new_cost_basis"] = ncb
            row_dict["locked_in_profit"] = lip
            row_dict["locked_in_profit_pct"] = lip_pct
            row_dict["pct_assigned"] = pa
            row_dict["pct_assigned_with_put"] = pawp
            rows.append(row_dict)

    return pd.DataFrame(rows)


def get_month_options(df: pd.DataFrame) -> list[tuple[str, str]]:
    """
    Return a list of (sort_key, display_label) tuples for the unique
    expiration months in *df*.

    Example: [("2025-10", "2025-10 (Oktober)"), ...]
    """
    tmp = df.copy()
    tmp["expiration_date"] = pd.to_datetime(tmp["expiration_date"])
    tmp["ym"] = tmp["expiration_date"].apply(lambda x: x.strftime("%Y-%m"))
    unique_months = sorted(tmp["ym"].unique())
    result = []
    for ym in unique_months:
        month_int = int(ym.split("-")[1])
        label = f"{ym} ({MONTH_MAP.get(month_int, '')})"
        result.append((ym, label))
    return result


def get_month_options_with_dte(df: pd.DataFrame) -> list[tuple[str, str]]:
    """
    Like :func:`get_month_options` but appends the typical DTE to the
    display label.

    Uses the **maximum** DTE within each month (= the monthly expiration).

    Example: [("2025-10", "Oktober 2025 (42 DTE)"), ...]
    """
    tmp = df.copy()
    tmp["expiration_date"] = pd.to_datetime(tmp["expiration_date"])
    tmp["ym"] = tmp["expiration_date"].apply(lambda x: x.strftime("%Y-%m"))

    # Max DTE per month (= the monthly opex)
    dte_per_month = tmp.groupby("ym")["days_to_expiration"].max().to_dict()

    unique_months = sorted(tmp["ym"].unique())
    result = []
    for ym in unique_months:
        month_int = int(ym.split("-")[1])
        year = ym.split("-")[0]
        dte = int(dte_per_month.get(ym, 0))
        label = f"{MONTH_MAP.get(month_int, ym)} {year} ({dte} DTE)"
        result.append((ym, label))
    return result


def filter_strikes_by_moneyness(
    df: pd.DataFrame,
    current_price: float,
    mode: str = "atm_20",
) -> pd.DataFrame:
    """
    Filter option rows by strike range relative to *current_price*.

    Modes:
        ``"all"``      – no filter
        ``"atm"``      – ATM only: strike between 95% and 105% of current price
        ``"atm_10"``   – ATM to 10% over: strike between 95% of price and +10%
        ``"atm_20"``   – ATM to 20% over: strike between 95% of price and +20%
        ``"atm_30"``   – ATM to 30% over: strike between 95% of price and +30%

    For **puts**, we want strikes *around and above* the current price
    (higher strike = more protection / more ITM).
    """
    if mode == "all" or df.empty:
        return df

    pct_map = {
        "atm": 0.05,
        "atm_10": 0.10,
        "atm_20": 0.20,
        "atm_30": 0.30,
    }
    pct = pct_map.get(mode, 0.20)

    lower = current_price * 0.95  # slightly below ATM
    upper = current_price * (1 + pct)

    return df[
        (df["strike_price"] >= lower) & (df["strike_price"] <= upper)
    ].copy()
