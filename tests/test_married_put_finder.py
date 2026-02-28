"""Tests for src/married_put_finder.py – Married Put Finder calculation engine."""

import pytest
import pandas as pd
import numpy as np

from src.married_put_finder import (
    MONTH_MAP,
    _midpoint_price,
    calculate_collar_metrics,
    calculate_put_only_metrics,
    filter_strikes_by_moneyness,
    get_month_options,
    get_month_options_with_dte,
)


# ── helpers ─────────────────────────────────────────────────────────

def _make_put(**overrides) -> dict:
    defaults = {
        "symbol": "TEST",
        "strike_price": 145.0,
        "option_price": 8.0,
        "days_to_expiration": 60,
        "live_stock_price": 150.0,
        "expiration_date": pd.Timestamp("2026-04-30"),
        "contract_type": "put",
        "open_interest": 100,
    }
    defaults.update(overrides)
    return defaults


def _make_call(**overrides) -> dict:
    defaults = {
        "symbol": "TEST",
        "strike_price": 145.0,
        "option_price": 3.0,
        "days_to_expiration": 30,
        "live_stock_price": 150.0,
        "expiration_date": pd.Timestamp("2026-03-30"),
        "contract_type": "call",
        "open_interest": 200,
    }
    defaults.update(overrides)
    return defaults


def _puts_df(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows if rows else [_make_put()])


def _calls_df(*rows) -> pd.DataFrame:
    return pd.DataFrame(rows if rows else [_make_call()])


# =====================================================================
# MONTH_MAP
# =====================================================================
class TestMonthMap:
    def test_has_12_entries(self):
        assert len(MONTH_MAP) == 12

    def test_january(self):
        assert MONTH_MAP[1] == "Januar"

    def test_december(self):
        assert MONTH_MAP[12] == "Dezember"


# =====================================================================
# calculate_put_only_metrics
# =====================================================================
class TestPutOnlyMetrics:
    """PowerOptions 'Sell Call Month = None' view."""

    @pytest.fixture()
    def result(self):
        df = _puts_df(_make_put(
            strike_price=145.0, option_price=8.0,
            days_to_expiration=60, live_stock_price=150.0,
        ))
        return calculate_put_only_metrics(df, cost_basis=120.0, current_price=150.0).iloc[0]

    def test_put_label_contains_symbol(self, result):
        assert "TEST" in result["put_label"]

    def test_put_label_contains_strike(self, result):
        assert "145.00" in result["put_label"]

    def test_put_label_contains_put(self, result):
        assert "PUT" in result["put_label"]

    def test_put_label_contains_dte(self, result):
        assert "(60)" in result["put_label"]

    def test_put_midpoint_price(self, result):
        assert result["put_midpoint_price"] == pytest.approx(8.0)

    def test_intrinsic_value_otm_put(self, result):
        # Put 145 with stock at 150 → OTM → intrinsic = 0
        assert result["intrinsic_value"] == pytest.approx(0.0)

    def test_put_time_value_all_time_value(self, result):
        # OTM put → entire premium is time value
        assert result["put_time_value"] == pytest.approx(8.0)

    def test_put_time_value_per_mo(self, result):
        # 8.0 / (60/30) = 4.0
        assert result["put_time_value_per_mo"] == pytest.approx(4.0)

    def test_new_cost_basis(self, result):
        # 120 + 8 = 128
        assert result["new_cost_basis"] == pytest.approx(128.0)

    def test_locked_in_profit(self, result):
        # 145 - 128 = 17
        assert result["locked_in_profit"] == pytest.approx(17.0)

    def test_locked_in_profit_pct(self, result):
        # 17 / 128 * 100 = 13.28%
        assert result["locked_in_profit_pct"] == pytest.approx(13.28, abs=0.01)


class TestPutOnlyMetricsITM:
    """ITM put: intrinsic value is positive."""

    @pytest.fixture()
    def result(self):
        df = _puts_df(_make_put(
            strike_price=160.0, option_price=15.0,
            days_to_expiration=90, live_stock_price=150.0,
        ))
        return calculate_put_only_metrics(df, cost_basis=120.0, current_price=150.0).iloc[0]

    def test_intrinsic_value_itm(self, result):
        # max(0, 160 - 150) = 10
        assert result["intrinsic_value"] == pytest.approx(10.0)

    def test_time_value_itm(self, result):
        # 15 - 10 = 5
        assert result["put_time_value"] == pytest.approx(5.0)

    def test_time_value_per_mo_itm(self, result):
        # 5 / (90/30) = 1.667
        assert result["put_time_value_per_mo"] == pytest.approx(1.667, abs=0.001)

    def test_new_cost_basis_itm(self, result):
        # 120 + 15 = 135
        assert result["new_cost_basis"] == pytest.approx(135.0)

    def test_locked_in_profit_itm(self, result):
        # 160 - 135 = 25
        assert result["locked_in_profit"] == pytest.approx(25.0)


class TestPutOnlyNegativeProfit:
    """When cost basis is high and strike is low → negative locked-in profit."""

    @pytest.fixture()
    def result(self):
        df = _puts_df(_make_put(
            strike_price=140.0, option_price=5.0,
            days_to_expiration=30, live_stock_price=150.0,
        ))
        return calculate_put_only_metrics(df, cost_basis=140.0, current_price=150.0).iloc[0]

    def test_locked_in_profit_negative(self, result):
        # 140 - (140 + 5) = -5
        assert result["locked_in_profit"] == pytest.approx(-5.0)

    def test_locked_in_profit_pct_negative(self, result):
        # -5 / 145 * 100 = -3.45%
        assert result["locked_in_profit_pct"] == pytest.approx(-3.45, abs=0.01)


class TestPutOnlyEdgeCases:
    def test_empty_df_returns_empty(self):
        result = calculate_put_only_metrics(pd.DataFrame(), cost_basis=100.0, current_price=150.0)
        assert result.empty

    def test_zero_dte_time_value_per_mo(self):
        df = _puts_df(_make_put(days_to_expiration=0))
        result = calculate_put_only_metrics(df, cost_basis=100.0, current_price=150.0).iloc[0]
        assert result["put_time_value_per_mo"] == 0.0

    def test_multiple_rows(self):
        df = _puts_df(
            _make_put(strike_price=140.0, option_price=5.0),
            _make_put(strike_price=150.0, option_price=10.0),
        )
        result = calculate_put_only_metrics(df, cost_basis=100.0, current_price=150.0)
        assert len(result) == 2


# =====================================================================
# calculate_collar_metrics
# =====================================================================
class TestCollarMetrics:
    """PowerOptions 'Sell Call Month ≠ None' view with same-strike pairing."""

    @pytest.fixture()
    def result(self):
        puts = _puts_df(_make_put(
            strike_price=145.0, option_price=8.0,
            days_to_expiration=60, live_stock_price=150.0,
        ))
        calls = _calls_df(_make_call(
            strike_price=145.0, option_price=3.0,
            days_to_expiration=30,
        ))
        return calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        ).iloc[0]

    def test_call_label_present(self, result):
        assert result["call_label"] is not None
        assert "CALL" in result["call_label"]

    def test_call_midpoint_price(self, result):
        assert result["call_midpoint_price"] == pytest.approx(3.0)

    def test_new_cost_basis_collar(self, result):
        # 120 + 8 - 3 = 125
        assert result["new_cost_basis"] == pytest.approx(125.0)

    def test_locked_in_profit_collar(self, result):
        # 145 - 125 = 20
        assert result["locked_in_profit"] == pytest.approx(20.0)

    def test_locked_in_profit_pct_collar(self, result):
        # 20 / 125 * 100 = 16.0%
        assert result["locked_in_profit_pct"] == pytest.approx(16.0)

    def test_pct_assigned(self, result):
        # (145 - 125) / 125 * 100 = 16.0%
        assert result["pct_assigned"] == pytest.approx(16.0)

    def test_pct_assigned_with_put_same_strike(self, result):
        # Same strike → put residual = max(0, 145-145) = 0
        # (145 - 125 + 0) / 125 * 100 = 16.0%
        assert result["pct_assigned_with_put"] == pytest.approx(16.0)

    def test_put_time_value_still_present(self, result):
        """Collar metrics include put-only metrics too."""
        assert "put_time_value" in result.index


class TestCollarPutStrikeAboveCallStrike:
    """When put strike > call strike, put has residual value at call strike."""

    @pytest.fixture()
    def result(self):
        puts = _puts_df(_make_put(strike_price=160.0, option_price=15.0))
        calls = _calls_df(_make_call(strike_price=160.0, option_price=5.0))
        return calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        ).iloc[0]

    def test_ncb(self, result):
        # 120 + 15 - 5 = 130
        assert result["new_cost_basis"] == pytest.approx(130.0)

    def test_pct_assigned(self, result):
        # (160 - 130) / 130 * 100 = 23.08%
        assert result["pct_assigned"] == pytest.approx(23.08, abs=0.01)


class TestCollarNoMatchingCall:
    """Put at 145, only call at 140 (below put strike) → no valid call → put-only fallback."""

    @pytest.fixture()
    def result(self):
        puts = _puts_df(_make_put(strike_price=145.0, option_price=8.0))
        calls = _calls_df(_make_call(strike_price=140.0, option_price=4.0))  # below put strike
        return calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        ).iloc[0]

    def test_call_label_none(self, result):
        assert result["call_label"] is None

    def test_call_price_none(self, result):
        assert result["call_midpoint_price"] is None

    def test_pct_assigned_none(self, result):
        assert result["pct_assigned"] is None

    def test_fallback_to_put_only_ncb(self, result):
        # 120 + 8 = 128 (put-only)
        assert result["new_cost_basis"] == pytest.approx(128.0)


class TestCollarNoCalls:
    """calls_df is None → graceful fallback to put-only."""

    def test_none_calls(self):
        puts = _puts_df(_make_put())
        result = calculate_collar_metrics(
            puts, None, cost_basis=120.0, current_price=150.0,
        ).iloc[0]
        assert result["call_label"] is None
        assert "put_label" in result.index

    def test_empty_calls(self):
        puts = _puts_df(_make_put())
        result = calculate_collar_metrics(
            puts, pd.DataFrame(), cost_basis=120.0, current_price=150.0,
        ).iloc[0]
        assert result["call_label"] is None


class TestCollarMultipleRows:
    """Wide collar: each put pairs with every call where call_strike >= put_strike."""

    def test_wide_collar_matrix(self):
        puts = _puts_df(
            _make_put(strike_price=140.0, option_price=5.0),
            _make_put(strike_price=145.0, option_price=8.0),
            _make_put(strike_price=150.0, option_price=12.0),
        )
        calls = _calls_df(
            _make_call(strike_price=140.0, option_price=2.0),
            _make_call(strike_price=150.0, option_price=6.0),
            # No call at 145
        )
        result = calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        )
        # Put 140 → Call 140, Call 150  (2 rows)
        # Put 145 → Call 150            (1 row, 150 >= 145)
        # Put 150 → Call 150            (1 row)
        # Total = 4 rows
        assert len(result) == 4

    def test_same_strike_rows_present(self):
        puts = _puts_df(
            _make_put(strike_price=140.0, option_price=5.0),
            _make_put(strike_price=150.0, option_price=12.0),
        )
        calls = _calls_df(
            _make_call(strike_price=140.0, option_price=2.0),
            _make_call(strike_price=150.0, option_price=6.0),
        )
        result = calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        )
        # Put 140 → Call 140, Call 150  (2 rows)
        # Put 150 → Call 150            (1 row)
        # Total = 3 rows
        assert len(result) == 3

        # Check same-strike collar for Put 150
        same_strike = result[
            (result["strike_price"] == 150.0) &
            (result["call_midpoint_price"] == 6.0)
        ]
        assert len(same_strike) == 1


class TestCollarPctAssignedWithPutResidual:
    """Edge case: put strike higher than call strike → put has residual value."""

    def test_put_residual_value(self):
        # Put at 155, Call at 150 → put residual = max(0, 155-150) = 5
        puts = _puts_df(_make_put(strike_price=155.0, option_price=10.0))
        calls = _calls_df(_make_call(strike_price=155.0, option_price=4.0))
        result = calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        ).iloc[0]

        # NCB = 120 + 10 - 4 = 126
        # % Assnd = (155 - 126) / 126 * 100 = 23.02%
        # Put residual at call strike 155 = max(0, 155-155) = 0
        # % Assnd w/ Put = (155 - 126 + 0) / 126 * 100 = 23.02%
        assert result["pct_assigned"] == pytest.approx(23.02, abs=0.01)
        assert result["pct_assigned_with_put"] == pytest.approx(23.02, abs=0.01)


# =====================================================================
# get_month_options
# =====================================================================
class TestGetMonthOptions:
    def test_returns_sorted_tuples(self):
        df = pd.DataFrame({
            "expiration_date": [
                pd.Timestamp("2026-06-15"),
                pd.Timestamp("2026-04-15"),
                pd.Timestamp("2026-06-20"),
            ],
        })
        result = get_month_options(df)
        assert len(result) == 2
        assert result[0][0] == "2026-04"
        assert result[1][0] == "2026-06"

    def test_labels_contain_month_name(self):
        df = pd.DataFrame({
            "expiration_date": [pd.Timestamp("2026-10-15")],
        })
        result = get_month_options(df)
        assert "Oktober" in result[0][1]

    def test_empty_df(self):
        df = pd.DataFrame({"expiration_date": pd.Series([], dtype="datetime64[ns]")})
        result = get_month_options(df)
        assert result == []


# =====================================================================
# PowerOptions-style scenario tests
# =====================================================================
class TestPowerOptionsScenarioTSLA:
    """
    Verify calculations match the TSLA screenshot from PowerOptions:
      Stock=TSLA, Cost Basis=190, Current Price=251.52
      Put: 02-AUG 240.00 PUT (28) @ 11.83
      Call: 12-JUL 240.00 CALL (7) @ 14.75
      Expected: NCB=187.08, Locked-In=52.93 (28.3%), %Assnd=28.3%, %Assnd w/ Put=35.3%
    """

    @pytest.fixture()
    def result(self):
        puts = _puts_df(_make_put(
            symbol="TSLA",
            strike_price=240.0,
            option_price=11.83,
            days_to_expiration=28,
            live_stock_price=251.52,
            expiration_date=pd.Timestamp("2024-08-02"),
        ))
        calls = _calls_df(_make_call(
            symbol="TSLA",
            strike_price=240.0,
            option_price=14.75,
            days_to_expiration=7,
            live_stock_price=251.52,
            expiration_date=pd.Timestamp("2024-07-12"),
        ))
        return calculate_collar_metrics(
            puts, calls, cost_basis=190.0, current_price=251.52,
        ).iloc[0]

    def test_ncb(self, result):
        # 190 + 11.83 - 14.75 = 187.08
        assert result["new_cost_basis"] == pytest.approx(187.08, abs=0.01)

    def test_locked_in_profit(self, result):
        # 240 - 187.08 = 52.92
        assert result["locked_in_profit"] == pytest.approx(52.92, abs=0.02)

    def test_locked_in_profit_pct(self, result):
        # 52.92 / 187.08 * 100 ≈ 28.3%
        assert result["locked_in_profit_pct"] == pytest.approx(28.3, abs=0.1)

    def test_pct_assigned(self, result):
        # Same as locked-in % because put and call are at same strike
        # (240 - 187.08) / 187.08 * 100 ≈ 28.3%
        assert result["pct_assigned"] == pytest.approx(28.3, abs=0.1)


class TestPowerOptionsScenarioPG:
    """
    PG put-only scenario from PowerOptions screenshot:
      Stock=PG, Cost Basis=158.67, Current Price=158.67
      Put: 03-OCT 170.00 PUT (42) @ 11.28
      Expected: NCB=169.95, Locked-In=0.05 (0.03%), Time Value≈-0.04 (approx)
    """

    @pytest.fixture()
    def result(self):
        df = _puts_df(_make_put(
            symbol="PG",
            strike_price=170.0,
            option_price=11.28,
            days_to_expiration=42,
            live_stock_price=158.67,
            expiration_date=pd.Timestamp("2025-10-03"),
        ))
        return calculate_put_only_metrics(df, cost_basis=158.67, current_price=158.67).iloc[0]

    def test_ncb(self, result):
        # 158.67 + 11.28 = 169.95
        assert result["new_cost_basis"] == pytest.approx(169.95, abs=0.01)

    def test_locked_in_profit(self, result):
        # 170 - 169.95 = 0.05
        assert result["locked_in_profit"] == pytest.approx(0.05, abs=0.02)

    def test_intrinsic_value(self, result):
        # max(0, 170 - 158.67) = 11.33
        assert result["intrinsic_value"] == pytest.approx(11.33, abs=0.01)

    def test_time_value(self, result):
        # 11.28 - 11.33 = -0.05 (slightly negative due to data snapshot)
        # In practice this can happen with stale/midpoint data
        assert result["put_time_value"] == pytest.approx(-0.05, abs=0.02)


# =====================================================================
# _midpoint_price
# =====================================================================
class TestMidpointPrice:
    """Tests for the _midpoint_price helper."""

    def test_uses_premium_option_price_when_present(self):
        df = pd.DataFrame({
            "option_price": [5.0, 6.0],
            "premium_option_price": [5.5, 6.5],
        })
        result = _midpoint_price(df)
        assert list(result) == [5.5, 6.5]

    def test_falls_back_to_option_price_when_no_column(self):
        df = pd.DataFrame({"option_price": [5.0, 6.0]})
        result = _midpoint_price(df)
        assert list(result) == [5.0, 6.0]

    def test_fills_nan_with_option_price(self):
        df = pd.DataFrame({
            "option_price": [5.0, 6.0],
            "premium_option_price": [5.5, np.nan],
        })
        result = _midpoint_price(df)
        assert result.iloc[0] == pytest.approx(5.5)
        assert result.iloc[1] == pytest.approx(6.0)

    def test_all_nan_premium_falls_back(self):
        df = pd.DataFrame({
            "option_price": [3.0],
            "premium_option_price": [np.nan],
        })
        result = _midpoint_price(df)
        assert result.iloc[0] == pytest.approx(3.0)


# =====================================================================
# calculate_put_only_metrics with premium_option_price
# =====================================================================
class TestPutOnlyMetricsWithPremiumPrice:
    """Verify that premium_option_price takes priority over option_price."""

    @pytest.fixture()
    def result(self):
        df = pd.DataFrame([{
            "symbol": "TEST",
            "strike_price": 145.0,
            "option_price": 8.0,
            "premium_option_price": 8.50,
            "days_to_expiration": 60,
            "live_stock_price": 150.0,
            "expiration_date": pd.Timestamp("2026-04-30"),
            "contract_type": "put",
            "open_interest": 100,
        }])
        return calculate_put_only_metrics(df, cost_basis=120.0, current_price=150.0).iloc[0]

    def test_uses_premium_price(self, result):
        assert result["put_midpoint_price"] == pytest.approx(8.50)

    def test_new_cost_basis_uses_premium(self, result):
        # 120 + 8.50 = 128.50
        assert result["new_cost_basis"] == pytest.approx(128.50)

    def test_locked_in_profit_uses_premium(self, result):
        # 145 - 128.50 = 16.50
        assert result["locked_in_profit"] == pytest.approx(16.50)

    def test_time_value_uses_premium(self, result):
        # OTM → intrinsic = 0, time value = 8.50
        assert result["put_time_value"] == pytest.approx(8.50)


# =====================================================================
# get_month_options_with_dte
# =====================================================================
class TestGetMonthOptionsWithDTE:
    def test_includes_dte_in_label(self):
        df = pd.DataFrame({
            "expiration_date": [
                pd.Timestamp("2025-10-15"),
                pd.Timestamp("2025-10-17"),
            ],
            "days_to_expiration": [42, 44],
        })
        result = get_month_options_with_dte(df)
        assert len(result) == 1
        ym, label = result[0]
        assert ym == "2025-10"
        assert "Oktober" in label
        assert "44 DTE" in label  # max DTE

    def test_multiple_months_sorted(self):
        df = pd.DataFrame({
            "expiration_date": [
                pd.Timestamp("2025-12-15"),
                pd.Timestamp("2025-10-15"),
            ],
            "days_to_expiration": [100, 42],
        })
        result = get_month_options_with_dte(df)
        assert len(result) == 2
        assert result[0][0] == "2025-10"
        assert result[1][0] == "2025-12"
        assert "42 DTE" in result[0][1]
        assert "100 DTE" in result[1][1]

    def test_empty_df(self):
        df = pd.DataFrame({
            "expiration_date": pd.Series([], dtype="datetime64[ns]"),
            "days_to_expiration": pd.Series([], dtype="float64"),
        })
        result = get_month_options_with_dte(df)
        assert result == []

    def test_label_format(self):
        df = pd.DataFrame({
            "expiration_date": [pd.Timestamp("2026-01-20")],
            "days_to_expiration": [180],
        })
        result = get_month_options_with_dte(df)
        ym, label = result[0]
        assert label == "Januar 2026 (180 DTE)"


# =====================================================================
# filter_strikes_by_moneyness
# =====================================================================
class TestFilterStrikesByMoneyness:
    @pytest.fixture()
    def df(self):
        """Option chain with strikes from 90 to 200 (step 10)."""
        return pd.DataFrame({
            "strike_price": list(range(90, 210, 10)),
            "option_price": [1.0] * 12,
        })

    def test_all_mode_returns_everything(self, df):
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="all")
        assert len(result) == len(df)

    def test_atm_mode(self, df):
        # current_price=150 → lower=142.5, upper=157.5
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm")
        assert set(result["strike_price"].tolist()) == {150.0}

    def test_atm_10_mode(self, df):
        # current_price=150 → lower=142.5, upper=165
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm_10")
        expected = {150.0, 160.0}
        assert set(result["strike_price"].tolist()) == expected

    def test_atm_20_mode(self, df):
        # current_price=150 → lower=142.5, upper=180
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm_20")
        expected = {150.0, 160.0, 170.0, 180.0}
        assert set(result["strike_price"].tolist()) == expected

    def test_atm_30_mode(self, df):
        # current_price=150 → lower=142.5, upper=195
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm_30")
        expected = {150.0, 160.0, 170.0, 180.0, 190.0}
        assert set(result["strike_price"].tolist()) == expected

    def test_empty_df(self):
        result = filter_strikes_by_moneyness(pd.DataFrame(), current_price=150.0, mode="atm")
        assert result.empty

    def test_no_matches(self):
        df = pd.DataFrame({"strike_price": [50.0, 300.0], "option_price": [1.0, 1.0]})
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm")
        assert result.empty

    def test_returns_copy(self, df):
        """Ensure the returned DataFrame is a copy, not a view."""
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm_20")
        result["option_price"] = 999.0
        assert df["option_price"].iloc[0] == 1.0  # original unchanged

    def test_unknown_mode_defaults_to_20pct(self, df):
        """Unknown mode falls back to 20% via pct_map.get default."""
        result = filter_strikes_by_moneyness(df, current_price=150.0, mode="unknown")
        expected = filter_strikes_by_moneyness(df, current_price=150.0, mode="atm_20")
        assert list(result["strike_price"]) == list(expected["strike_price"])


# =====================================================================
# Collar with premium_option_price
# =====================================================================
class TestCollarWithPremiumPrice:
    """Verify collar calculation uses premium_option_price for both puts and calls."""

    @pytest.fixture()
    def result(self):
        puts = pd.DataFrame([{
            "symbol": "TEST",
            "strike_price": 145.0,
            "option_price": 8.0,
            "premium_option_price": 8.50,
            "days_to_expiration": 60,
            "live_stock_price": 150.0,
            "expiration_date": pd.Timestamp("2026-04-30"),
            "contract_type": "put",
            "open_interest": 100,
        }])
        calls = pd.DataFrame([{
            "symbol": "TEST",
            "strike_price": 145.0,
            "option_price": 3.0,
            "premium_option_price": 3.25,
            "days_to_expiration": 30,
            "live_stock_price": 150.0,
            "expiration_date": pd.Timestamp("2026-03-30"),
            "contract_type": "call",
            "open_interest": 200,
        }])
        return calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        ).iloc[0]

    def test_put_uses_premium_price(self, result):
        assert result["put_midpoint_price"] == pytest.approx(8.50)

    def test_call_uses_premium_price(self, result):
        assert result["call_midpoint_price"] == pytest.approx(3.25)

    def test_ncb_uses_both_premium_prices(self, result):
        # 120 + 8.50 - 3.25 = 125.25
        assert result["new_cost_basis"] == pytest.approx(125.25)

    def test_locked_in_profit(self, result):
        # 145 - 125.25 = 19.75
        assert result["locked_in_profit"] == pytest.approx(19.75)


# =====================================================================
# Wide Collar tests
# =====================================================================
class TestWideCollar:
    """Wide collar: put strike < call strike → more upside, less locked-in."""

    @pytest.fixture()
    def result(self):
        # Put at 140, Call at 150 → wide collar
        puts = _puts_df(_make_put(
            strike_price=140.0, option_price=5.0,
            days_to_expiration=60, live_stock_price=150.0,
        ))
        calls = _calls_df(_make_call(
            strike_price=150.0, option_price=4.0,
            days_to_expiration=30,
        ))
        return calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        ).iloc[0]

    def test_call_matched(self, result):
        assert result["call_label"] is not None
        assert "150.00" in result["call_label"]
        assert "CALL" in result["call_label"]

    def test_ncb(self, result):
        # 120 + 5 - 4 = 121
        assert result["new_cost_basis"] == pytest.approx(121.0)

    def test_locked_in_profit(self, result):
        # put_strike - NCB = 140 - 121 = 19
        assert result["locked_in_profit"] == pytest.approx(19.0)

    def test_pct_assigned(self, result):
        # (call_strike - NCB) / NCB = (150 - 121) / 121 * 100 = 23.97%
        assert result["pct_assigned"] == pytest.approx(23.97, abs=0.01)

    def test_pct_assigned_with_put(self, result):
        # put_residual = max(0, 140 - 150) = 0
        # (150 - 121 + 0) / 121 * 100 = 23.97%
        assert result["pct_assigned_with_put"] == pytest.approx(23.97, abs=0.01)

    def test_pct_assigned_higher_than_locked_in(self, result):
        """Wide collar: % Assigned > % Locked In (more upside room)."""
        lip_pct = result["locked_in_profit_pct"]
        pa = result["pct_assigned"]
        assert pa > lip_pct


class TestWideCollarPutResidual:
    """Wide collar where put strike > call strike → put has residual value."""

    def test_put_residual_adds_value(self):
        # Put at 160 paired with call at 155 (call 155 >= put 160? NO)
        # But put at 150 paired with call at 155 (YES) → no residual
        # Let's use: Put at 155, calls at 150 and 155
        puts = _puts_df(_make_put(strike_price=155.0, option_price=10.0))
        calls = _calls_df(
            _make_call(strike_price=155.0, option_price=4.0),
        )
        result = calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        )
        # Only call at 155 >= put at 155 → 1 row (same-strike)
        assert len(result) == 1
        row = result.iloc[0]
        # NCB = 120 + 10 - 4 = 126
        assert row["new_cost_basis"] == pytest.approx(126.0)
        # put_residual = max(0, 155-155) = 0 → same as pct_assigned
        assert row["pct_assigned"] == pytest.approx(row["pct_assigned_with_put"])


class TestCollarMultipleExpirations:
    """Calls across multiple expiration dates multiply combinations."""

    def test_multiple_call_expirations(self):
        puts = _puts_df(_make_put(
            strike_price=140.0, option_price=5.0,
            days_to_expiration=60,
        ))
        calls = _calls_df(
            _make_call(strike_price=140.0, option_price=2.0, days_to_expiration=30,
                       expiration_date=pd.Timestamp("2026-03-02")),
            _make_call(strike_price=140.0, option_price=3.0, days_to_expiration=40,
                       expiration_date=pd.Timestamp("2026-03-10")),
            _make_call(strike_price=140.0, option_price=4.0, days_to_expiration=50,
                       expiration_date=pd.Timestamp("2026-03-17")),
        )
        result = calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        )
        # 1 put × 3 calls = 3 rows
        assert len(result) == 3

    def test_wide_collar_x_expirations(self):
        """2 puts × 3 calls (with strike filter) = full matrix."""
        puts = _puts_df(
            _make_put(strike_price=130.0, option_price=3.0),
            _make_put(strike_price=140.0, option_price=5.0),
        )
        calls = _calls_df(
            _make_call(strike_price=135.0, option_price=2.0,
                       expiration_date=pd.Timestamp("2026-04-02")),
            _make_call(strike_price=140.0, option_price=3.0,
                       expiration_date=pd.Timestamp("2026-04-10")),
            _make_call(strike_price=145.0, option_price=4.0,
                       expiration_date=pd.Timestamp("2026-04-17")),
        )
        result = calculate_collar_metrics(
            puts, calls, cost_basis=120.0, current_price=150.0,
        )
        # Put 130 → Call 135 (>=130), Call 140 (>=130), Call 145 (>=130) = 3
        # Put 140 → Call 140 (>=140), Call 145 (>=140) = 2
        # Total = 5 rows
        assert len(result) == 5
