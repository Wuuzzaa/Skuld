import pandas as pd
import pytest
from src.spread_checklist import ChecklistThresholds, evaluate_checklist


def _make_row(**kwargs) -> dict:
    base = {
        "iv_rank": 50.0,
        "sell_delta": -0.16,
        "days_to_expiration": 14,
        "max_profit%": 40.0,
        "earnings_date": "2099-01-01",
        "expiration_date": "2026-12-31",
    }
    base.update(kwargs)
    return base


def _eval(row_dict) -> pd.Series:
    df = pd.DataFrame([row_dict])
    return evaluate_checklist(df).iloc[0]


# ── IV Rank ──────────────────────────────────────────────────────────────────

def test_iv_rank_green():
    row = _eval(_make_row(iv_rank=35.0))
    assert row["chk_iv_rank"] == "g"


def test_iv_rank_yellow():
    row = _eval(_make_row(iv_rank=22.0))
    assert row["chk_iv_rank"] == "y"


def test_iv_rank_red():
    row = _eval(_make_row(iv_rank=5.0))
    assert row["chk_iv_rank"] == "r"


def test_iv_rank_nan():
    row = _eval(_make_row(iv_rank=float("nan")))
    assert row["chk_iv_rank"] == "n"


# ── Short Delta ───────────────────────────────────────────────────────────────

def test_delta_green():
    row = _eval(_make_row(sell_delta=-0.16))
    assert row["chk_delta"] == "g"


def test_delta_yellow():
    row = _eval(_make_row(sell_delta=-0.25))
    assert row["chk_delta"] == "y"


def test_delta_red():
    row = _eval(_make_row(sell_delta=-0.50))
    assert row["chk_delta"] == "r"


def test_delta_nan():
    row = _eval(_make_row(sell_delta=float("nan")))
    assert row["chk_delta"] == "n"


# ── DTE ──────────────────────────────────────────────────────────────────────

def test_dte_green():
    row = _eval(_make_row(days_to_expiration=14))
    assert row["chk_dte"] == "g"


def test_dte_yellow():
    row = _eval(_make_row(days_to_expiration=30))
    assert row["chk_dte"] == "y"


def test_dte_red():
    row = _eval(_make_row(days_to_expiration=60))
    assert row["chk_dte"] == "r"


def test_dte_nan():
    row = _eval(_make_row(days_to_expiration=float("nan")))
    assert row["chk_dte"] == "n"


# ── Credit / Breite ───────────────────────────────────────────────────────────

def test_credit_green():
    row = _eval(_make_row(**{"max_profit%": 40.0}))
    assert row["chk_credit"] == "g"


def test_credit_yellow():
    row = _eval(_make_row(**{"max_profit%": 25.0}))
    assert row["chk_credit"] == "y"


def test_credit_red():
    row = _eval(_make_row(**{"max_profit%": 10.0}))
    assert row["chk_credit"] == "r"


def test_credit_nan():
    row = _eval(_make_row(**{"max_profit%": float("nan")}))
    assert row["chk_credit"] == "n"


# ── Earnings ─────────────────────────────────────────────────────────────────

def test_earnings_green_no_earnings_before_expiry():
    row = _eval(_make_row(earnings_date="2099-12-31", expiration_date="2026-12-31"))
    assert row["chk_earnings"] == "g"


def test_earnings_red_earnings_before_expiry():
    row = _eval(_make_row(earnings_date="2026-11-01", expiration_date="2026-12-31"))
    assert row["chk_earnings"] == "r"


def test_earnings_nan_earnings_date():
    row = _eval(_make_row(earnings_date=float("nan")))
    assert row["chk_earnings"] == "n"


# ── chk_full and chk_score ───────────────────────────────────────────────────

def test_chk_full_when_all_green():
    row = _eval(_make_row())
    assert bool(row["chk_full"]) is True
    assert row["chk_score"] == 5


def test_chk_full_false_when_one_red():
    row = _eval(_make_row(iv_rank=5.0))
    assert bool(row["chk_full"]) is False
    assert row["chk_score"] == 4


# ── Input DataFrame unchanged ────────────────────────────────────────────────

def test_input_df_unchanged():
    df = pd.DataFrame([_make_row()])
    original_cols = set(df.columns)
    evaluate_checklist(df)
    assert set(df.columns) == original_cols, "evaluate_checklist must not modify the input DataFrame"


# ── Custom thresholds ─────────────────────────────────────────────────────────

def test_custom_thresholds():
    t = ChecklistThresholds(min_iv_rank=50.0)
    df = pd.DataFrame([_make_row(iv_rank=40.0)])
    result = evaluate_checklist(df, t)
    assert result.iloc[0]["chk_iv_rank"] == "y"
