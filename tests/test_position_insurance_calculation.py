import pytest
import pandas as pd
import numpy as np
from src.position_insurance_calculation import calculate_position_insurance_metrics, calculate_collar_metrics


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


# ===================================================================
# Collar Tests (Teil B)
# ===================================================================

def _make_put_df_with_metrics(**overrides):
    """Helper: creates a single-row put DataFrame already enriched with Married-Put metrics."""
    df = _make_df(**overrides)
    cost_basis = overrides.get('cost_basis', 120.0)
    return calculate_position_insurance_metrics(df, cost_basis=cost_basis)


class TestCollarSpecExample:
    """
    Testfall 2 from spec: Collar with Call.
    
    Input:
      live_stock_price = 150.00, strike_price = 145.00, option_price = 8.00
      cost_basis = 120.00, days_to_expiration = 60
      call_strike = 160.00, call_price = 3.50
    
    Expected:
      collar_new_cost_basis     = 120 + 8 - 3.50 = 124.50
      collar_locked_in_profit   = 145 - 124.50 = 20.50
      collar_locked_in_profit_pct = (20.50 / 124.50) * 100 = 16.47%
      collar_net_cost           = 8 - 3.50 = 4.50 (Debit)
      collar_max_profit         = 160 - 124.50 = 35.50
      collar_max_profit_pct     = (35.50 / 124.50) * 100 = 28.51%
      pct_assigned              = 28.51%
      put_value_at_call_strike  = max(0, 145 - 160) = 0
      pct_assigned_with_put     = (160 - 124.50 + 0) / 124.50 * 100 = 28.51%
    """

    @pytest.fixture()
    def result(self):
        put_df = _make_put_df_with_metrics(
            live_stock_price=150.0, strike_price=145.0,
            option_price=8.0, days_to_expiration=60, cost_basis=120.0
        )
        return calculate_collar_metrics(put_df, call_price=3.50, call_strike=160.0, cost_basis=120.0).iloc[0]

    def test_collar_new_cost_basis(self, result):
        assert result['collar_new_cost_basis'] == pytest.approx(124.50)

    def test_collar_locked_in_profit(self, result):
        assert result['collar_locked_in_profit'] == pytest.approx(20.50)

    def test_collar_locked_in_profit_pct(self, result):
        assert result['collar_locked_in_profit_pct'] == pytest.approx(16.47, abs=0.01)

    def test_collar_net_cost(self, result):
        assert result['collar_net_cost'] == pytest.approx(4.50)

    def test_collar_max_profit(self, result):
        assert result['collar_max_profit'] == pytest.approx(35.50)

    def test_collar_max_profit_pct(self, result):
        assert result['collar_max_profit_pct'] == pytest.approx(28.51, abs=0.01)

    def test_pct_assigned(self, result):
        assert result['pct_assigned'] == pytest.approx(28.51, abs=0.01)

    def test_pct_assigned_with_put(self, result):
        # put_value_at_call_strike = max(0, 145 - 160) = 0
        assert result['pct_assigned_with_put'] == pytest.approx(28.51, abs=0.01)


class TestCostlessCollar:
    """
    Testfall 3 from spec: Costless Collar (put price == call price).
    
    Input:
      cost_basis = 120.00, put_strike = 145.00, put_price = 5.00
      call_strike = 155.00, call_price = 5.00
    
    Expected:
      collar_new_cost_basis   = 120 + 5 - 5 = 120.00
      collar_net_cost         = 5 - 5 = 0.00 (Costless)
      collar_locked_in_profit = 145 - 120 = 25.00
      collar_max_profit       = 155 - 120 = 35.00
    """

    @pytest.fixture()
    def result(self):
        put_df = _make_put_df_with_metrics(
            live_stock_price=150.0, strike_price=145.0,
            option_price=5.0, days_to_expiration=60, cost_basis=120.0
        )
        return calculate_collar_metrics(put_df, call_price=5.0, call_strike=155.0, cost_basis=120.0).iloc[0]

    def test_collar_net_cost_zero(self, result):
        assert result['collar_net_cost'] == pytest.approx(0.0)

    def test_collar_new_cost_basis(self, result):
        assert result['collar_new_cost_basis'] == pytest.approx(120.0)

    def test_collar_locked_in_profit(self, result):
        assert result['collar_locked_in_profit'] == pytest.approx(25.0)

    def test_collar_max_profit(self, result):
        assert result['collar_max_profit'] == pytest.approx(35.0)


class TestCollarNetCredit:
    """Call premium > Put premium → net credit collar."""

    def test_net_credit_is_negative(self):
        put_df = _make_put_df_with_metrics(
            live_stock_price=150.0, strike_price=140.0,
            option_price=3.0, days_to_expiration=30, cost_basis=120.0
        )
        result = calculate_collar_metrics(put_df, call_price=5.0, call_strike=155.0, cost_basis=120.0).iloc[0]
        # collar_net_cost = 3 - 5 = -2 (Credit)
        assert result['collar_net_cost'] == pytest.approx(-2.0)
        # collar_new_cost_basis = 120 + 3 - 5 = 118
        assert result['collar_new_cost_basis'] == pytest.approx(118.0)


class TestCollarPutStrikeAboveCallStrike:
    """Edge case: put strike > call strike (unusual but possible)."""

    def test_pct_assigned_with_put_includes_put_value(self):
        put_df = _make_put_df_with_metrics(
            live_stock_price=150.0, strike_price=160.0,
            option_price=15.0, days_to_expiration=60, cost_basis=120.0
        )
        result = calculate_collar_metrics(put_df, call_price=4.0, call_strike=155.0, cost_basis=120.0).iloc[0]
        # collar_new_cost_basis = 120 + 15 - 4 = 131
        assert result['collar_new_cost_basis'] == pytest.approx(131.0)
        # put_value_at_call_strike = max(0, 160 - 155) = 5
        # pct_assigned_with_put = (155 - 131 + 5) / 131 * 100 = 29/131*100 = 22.14
        assert result['pct_assigned_with_put'] == pytest.approx(22.14, abs=0.01)
        # pct_assigned (without put) = (155 - 131) / 131 * 100 = 24/131*100 = 18.32
        assert result['pct_assigned'] == pytest.approx(18.32, abs=0.01)


class TestCollarEdgeCases:
    """Edge cases for collar calculations."""

    def test_empty_dataframe(self):
        result = calculate_collar_metrics(pd.DataFrame(), call_price=3.0, call_strike=160.0, cost_basis=120.0)
        assert result.empty

    def test_multiple_put_rows(self):
        """Collar metrics applied to all put rows with the same call."""
        df = pd.DataFrame([
            {'strike_price': 145.0, 'option_price': 8.0, 'days_to_expiration': 60, 'live_stock_price': 150.0},
            {'strike_price': 140.0, 'option_price': 5.0, 'days_to_expiration': 60, 'live_stock_price': 150.0},
        ])
        df = calculate_position_insurance_metrics(df, cost_basis=120.0)
        result = calculate_collar_metrics(df, call_price=3.50, call_strike=160.0, cost_basis=120.0)
        assert len(result) == 2
        # Row 0: collar_new_cost_basis = 120 + 8 - 3.5 = 124.5
        assert result.iloc[0]['collar_new_cost_basis'] == pytest.approx(124.5)
        # Row 1: collar_new_cost_basis = 120 + 5 - 3.5 = 121.5
        assert result.iloc[1]['collar_new_cost_basis'] == pytest.approx(121.5)
        # Both share same collar_net_cost per row (different put prices)
        assert result.iloc[0]['collar_net_cost'] == pytest.approx(4.5)  # 8 - 3.5
        assert result.iloc[1]['collar_net_cost'] == pytest.approx(1.5)  # 5 - 3.5

    def test_no_helper_column_leaks(self):
        """Ensure _put_value_at_call_strike helper column is cleaned up."""
        put_df = _make_put_df_with_metrics(
            live_stock_price=150.0, strike_price=145.0,
            option_price=8.0, days_to_expiration=60, cost_basis=120.0
        )
        result = calculate_collar_metrics(put_df, call_price=3.50, call_strike=160.0, cost_basis=120.0)
        assert '_put_value_at_call_strike' not in result.columns
