import pytest
import pandas as pd
import numpy as np
from src.position_insurance_calculation import calculate_position_insurance_metrics


def _make_df(**overrides):
    """Helper: creates a single-row DataFrame with sensible defaults."""
    defaults = {
        'strike_price': 145.0,
        'option_price': 8.0,
        'days_to_expiration': 60,
        'live_stock_price': 150.0,
        'expiration_date': pd.Timestamp('2026-04-30'),
        'symbol': 'TEST',
    }
    defaults.update(overrides)
    return pd.DataFrame([defaults])


class TestSpecificationExample:
    """Validates the exact numbers from the specification document."""

    @pytest.fixture()
    def result(self):
        df = _make_df(live_stock_price=150.0, strike_price=145.0, option_price=8.0, days_to_expiration=60)
        return calculate_position_insurance_metrics(df, cost_basis=120.0).iloc[0]

    # --- Existing metrics ---
    def test_new_cost_basis(self, result):
        assert result['new_cost_basis'] == pytest.approx(128.0)

    def test_locked_in_profit(self, result):
        assert result['locked_in_profit'] == pytest.approx(17.0)

    def test_locked_in_profit_pct(self, result):
        assert result['locked_in_profit_pct'] == pytest.approx(13.28, abs=0.01)

    def test_risk_pct_zero_when_profit_positive(self, result):
        assert result['risk_pct'] == pytest.approx(0.0)

    def test_intrinsic_value(self, result):
        assert result['intrinsic_value'] == pytest.approx(0.0)

    def test_time_value(self, result):
        assert result['time_value'] == pytest.approx(8.0)

    def test_time_value_per_month(self, result):
        assert result['time_value_per_month'] == pytest.approx(4.0)

    # --- New metrics ---
    def test_insurance_cost_pct(self, result):
        # (8 / 150) * 100 = 5.333...
        assert result['insurance_cost_pct'] == pytest.approx(5.33, abs=0.01)

    def test_downside_protection_pct(self, result):
        # ((150 - 145) / 150) * 100 = 3.333...
        assert result['downside_protection_pct'] == pytest.approx(3.33, abs=0.01)

    def test_annualized_cost(self, result):
        # (8 / 60) * 365 = 48.6666...
        assert result['annualized_cost'] == pytest.approx(48.67, abs=0.01)

    def test_annualized_cost_pct(self, result):
        # (48.6666 / 150) * 100 = 32.444...
        assert result['annualized_cost_pct'] == pytest.approx(32.44, abs=0.01)

    def test_upside_drag_pct(self, result):
        # Same as insurance_cost_pct
        assert result['upside_drag_pct'] == pytest.approx(5.33, abs=0.01)


class TestITMPut:
    """Put that is in-the-money (strike > stock price)."""

    def test_itm_downside_protection_is_negative(self):
        df = _make_df(live_stock_price=150.0, strike_price=155.0, option_price=10.0, days_to_expiration=45)
        result = calculate_position_insurance_metrics(df, cost_basis=130.0).iloc[0]
        # ((150 - 155) / 150) * 100 = -3.33
        assert result['downside_protection_pct'] == pytest.approx(-3.33, abs=0.01)

    def test_itm_intrinsic_value(self):
        df = _make_df(live_stock_price=150.0, strike_price=155.0, option_price=10.0, days_to_expiration=45)
        result = calculate_position_insurance_metrics(df, cost_basis=130.0).iloc[0]
        assert result['intrinsic_value'] == pytest.approx(5.0)
        assert result['time_value'] == pytest.approx(5.0)  # 10 - 5


class TestNegativeLockedInProfit:
    """When cost_basis is high enough that locked_in_profit becomes negative."""

    def test_risk_pct_when_loss(self):
        df = _make_df(strike_price=100.0, option_price=5.0, live_stock_price=110.0, days_to_expiration=30)
        result = calculate_position_insurance_metrics(df, cost_basis=110.0).iloc[0]
        # new_cost_basis = 110 + 5 = 115
        # locked_in_profit = 100 - 115 = -15
        # risk_pct = 15/115 * 100 = 13.04
        assert result['locked_in_profit'] == pytest.approx(-15.0)
        assert result['risk_pct'] == pytest.approx(13.04, abs=0.01)


class TestEdgeCases:
    """Edge cases: zero DTE, empty DF, missing columns."""

    def test_zero_days_to_expiration(self):
        df = _make_df(days_to_expiration=0)
        result = calculate_position_insurance_metrics(df, cost_basis=120.0).iloc[0]
        assert result['time_value_per_month'] == 0
        assert result['annualized_cost'] == 0
        assert result['annualized_cost_pct'] == 0

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        result = calculate_position_insurance_metrics(df, cost_basis=100.0)
        assert result.empty

    def test_missing_column_returns_unchanged(self):
        df = pd.DataFrame([{'strike_price': 100.0, 'option_price': 5.0}])
        result = calculate_position_insurance_metrics(df, cost_basis=100.0)
        # Should return the original df without new columns (missing live_stock_price etc.)
        assert 'new_cost_basis' not in result.columns

    def test_multiple_rows(self):
        """Verify vectorized calculation works across multiple rows."""
        df = pd.DataFrame([
            {'strike_price': 145.0, 'option_price': 8.0, 'days_to_expiration': 60, 'live_stock_price': 150.0},
            {'strike_price': 140.0, 'option_price': 5.0, 'days_to_expiration': 30, 'live_stock_price': 150.0},
        ])
        result = calculate_position_insurance_metrics(df, cost_basis=120.0)
        assert len(result) == 2
        # Row 0
        assert result.iloc[0]['insurance_cost_pct'] == pytest.approx(5.33, abs=0.01)
        # Row 1: (5/150)*100 = 3.33
        assert result.iloc[1]['insurance_cost_pct'] == pytest.approx(3.33, abs=0.01)
        # Row 1 downside: ((150-140)/150)*100 = 6.67
        assert result.iloc[1]['downside_protection_pct'] == pytest.approx(6.67, abs=0.01)
