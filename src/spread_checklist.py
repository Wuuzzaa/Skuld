from __future__ import annotations

import pandas as pd
from dataclasses import dataclass


@dataclass
class ChecklistThresholds:
    min_iv_rank: float = 30.0       # %
    delta_min: float = 0.12
    delta_max: float = 0.20
    dte_min: int = 7
    dte_max: int = 21
    min_credit_pct: float = 33.0    # max_profit% = Credit / Breite


def _eval_iv_rank(val, t: ChecklistThresholds) -> str:
    if pd.isna(val):
        return "n"
    if val >= t.min_iv_rank:
        return "g"
    if val >= t.min_iv_rank - 10:
        return "y"
    return "r"


def _eval_delta(val, t: ChecklistThresholds) -> str:
    if pd.isna(val):
        return "n"
    abs_val = abs(val)
    if t.delta_min <= abs_val <= t.delta_max:
        return "g"
    if abs_val <= 0.30:
        return "y"
    return "r"


def _eval_dte(val, t: ChecklistThresholds) -> str:
    if pd.isna(val):
        return "n"
    try:
        v = int(val)
    except (TypeError, ValueError):
        return "n"
    if t.dte_min <= v <= t.dte_max:
        return "g"
    if v <= 45:
        return "y"
    return "r"


def _eval_credit(val, t: ChecklistThresholds) -> str:
    if pd.isna(val):
        return "n"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "n"
    if v >= t.min_credit_pct:
        return "g"
    if v >= 20.0:
        return "y"
    return "r"


def _eval_earnings(earnings_date, expiration_date) -> str:
    if pd.isna(earnings_date) or earnings_date == "" or pd.isna(expiration_date) or expiration_date == "":
        return "n"
    try:
        ed = pd.to_datetime(earnings_date)
        exp = pd.to_datetime(expiration_date)
    except Exception:
        return "n"
    today = pd.Timestamp.now().normalize()
    if ed >= today and ed <= exp:
        return "r"
    return "g"


def evaluate_checklist(df: pd.DataFrame, t: ChecklistThresholds | None = None) -> pd.DataFrame:
    """Appends checklist columns to a copy of df. Does not modify the original."""
    if t is None:
        t = ChecklistThresholds()

    result = df.copy()

    result["chk_iv_rank"] = df["iv_rank"].apply(lambda v: _eval_iv_rank(v, t)) if "iv_rank" in df.columns else "n"
    result["chk_delta"] = df["sell_delta"].apply(lambda v: _eval_delta(v, t)) if "sell_delta" in df.columns else "n"
    result["chk_dte"] = df["days_to_expiration"].apply(lambda v: _eval_dte(v, t)) if "days_to_expiration" in df.columns else "n"
    result["chk_credit"] = df["max_profit%"].apply(lambda v: _eval_credit(v, t)) if "max_profit%" in df.columns else "n"

    if "earnings_date" in df.columns and "expiration_date" in df.columns:
        result["chk_earnings"] = [
            _eval_earnings(row["earnings_date"], row["expiration_date"])
            for _, row in df.iterrows()
        ]
    else:
        result["chk_earnings"] = "n"

    checklist_cols = ["chk_iv_rank", "chk_delta", "chk_dte", "chk_credit", "chk_earnings"]
    result["chk_score"] = result[checklist_cols].apply(lambda row: sum(1 for v in row if v == "g"), axis=1)
    result["chk_full"] = result["chk_score"] == 5

    return result
