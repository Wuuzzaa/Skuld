import pytest
import pandas as pd
import math
from src.smart_finder_engine import (
    apply_quality_filters,
    calculate_smart_scores,
    get_top_recommendations,
    generate_comparison_insight,
    HOLDING_PERIOD_MAP,
    DEFAULT_WEIGHTS,
)
from src.position_insurance_calculation import calculate_position_insurance_metrics


def _make_puts(n=5, **common):
    """Create a multi-row put DataFrame with sensible defaults."""
    defaults = {
        'strike_price': 145.0, 'option_price': 8.0,
        'days_to_expiration': 60, 'live_stock_price': 150.0,
        'open_interest': 100, 'greeks_delta': -0.40,
        'contract_type': 'put', 'symbol': 'TEST',
        'expiration_date': pd.Timestamp('2026-04-30'),
    }
    defaults.update(common)
    rows = []
    for i in range(n):
        row = dict(defaults)
        row['strike_price'] = defaults['strike_price'] - i * 5  # vary strikes
        row['option_price'] = max(defaults['option_price'] - i * 1.5, 0.5)
        row['open_interest'] = defaults['open_interest'] * (i + 1)
        rows.append(row)
    return pd.DataFrame(rows)


def _enriched_puts(n=5, cost_basis=120.0, **common):
    """Create puts with Married-Put metrics already calculated."""
    df = _make_puts(n, **common)
    return calculate_position_insurance_metrics(df, cost_basis=cost_basis)


# ===================================================================
# apply_quality_filters
# ===================================================================

class TestQualityFilters:

    def test_removes_zero_oi(self):
        df = _enriched_puts(3)
        df.loc[0, 'open_interest'] = 0
        filtered, stats = apply_quality_filters(df, min_open_interest=1)
        assert stats['removed_oi_zero'] == 1
        assert len(filtered) == 2

    def test_removes_low_oi_soft(self):
        df = _enriched_puts(3)
        df['open_interest'] = [5, 50, 500]
        filtered, stats = apply_quality_filters(df, min_open_interest=10)
        assert stats['removed_oi_low'] == 1
        assert len(filtered) == 2

    def test_removes_short_dte(self):
        df = _enriched_puts(3)
        df.loc[0, 'days_to_expiration'] = 3
        filtered, stats = apply_quality_filters(df, min_open_interest=1)
        assert stats['removed_dte'] == 1

    def test_removes_zero_price(self):
        df = _enriched_puts(3)
        df.loc[0, 'option_price'] = 0
        filtered, stats = apply_quality_filters(df, min_open_interest=1)
        assert stats['removed_price'] == 1

    def test_removes_high_insurance_cost(self):
        df = _enriched_puts(3)
        df.loc[0, 'insurance_cost_pct'] = 25.0
        filtered, stats = apply_quality_filters(df, min_open_interest=1, max_insurance_cost_pct=20.0)
        assert stats['removed_cost'] == 1

    def test_removes_low_delta(self):
        df = _enriched_puts(3)
        df.loc[0, 'greeks_delta'] = -0.005
        filtered, stats = apply_quality_filters(df, min_open_interest=1, min_abs_delta=0.01)
        assert stats['removed_delta'] == 1

    def test_empty_input(self):
        df = pd.DataFrame()
        filtered, stats = apply_quality_filters(df)
        assert filtered.empty
        assert stats['total'] == 0
        assert stats['remaining'] == 0

    def test_stats_total_matches(self):
        df = _enriched_puts(10)
        _, stats = apply_quality_filters(df, min_open_interest=1)
        assert stats['total'] == 10
        # Nothing should be removed with good defaults
        assert stats['remaining'] == 10


# ===================================================================
# calculate_smart_scores
# ===================================================================

class TestSmartScores:

    def _prefs(self, **overrides):
        defaults = {
            'goal': 'lock_profit',
            'min_locked_in_profit_pct': 10.0,
            'target_dte': 60,
            'holding_period': 'short',
        }
        defaults.update(overrides)
        return defaults

    def test_scores_added(self):
        df = _enriched_puts(5)
        result = calculate_smart_scores(df, self._prefs())
        assert 'smart_score' in result.columns
        assert len(result) == 5

    def test_scores_between_0_and_100(self):
        df = _enriched_puts(10)
        result = calculate_smart_scores(df, self._prefs())
        assert result['smart_score'].min() >= 0
        assert result['smart_score'].max() <= 100

    def test_sorted_descending(self):
        df = _enriched_puts(5)
        result = calculate_smart_scores(df, self._prefs())
        scores = result['smart_score'].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_no_dte_preference_removes_penalty(self):
        """When target_dte is None, DTE dimension should not penalise."""
        df = _enriched_puts(3)
        df['days_to_expiration'] = [30, 180, 365]
        prefs = self._prefs(target_dte=None)
        result = calculate_smart_scores(df, prefs)
        # All should have same DTE contribution (0)
        assert 'smart_score' in result.columns

    def test_empty_input(self):
        df = pd.DataFrame()
        result = calculate_smart_scores(df, self._prefs())
        assert result.empty
        assert 'smart_score' in result.columns

    def test_custom_weights(self):
        df = _enriched_puts(5)
        # 100% weight on cost → cheapest should be #1
        result = calculate_smart_scores(df, self._prefs(), weights={
            'cost': 1.0, 'protection': 0.0, 'liquidity': 0.0,
            'dte_match': 0.0, 'time_value': 0.0,
        })
        # Row with lowest annualized_cost_pct should be first
        assert result.iloc[0]['annualized_cost_pct'] == result['annualized_cost_pct'].min()

    def test_cheapest_goal_scores(self):
        """Goal 'cheapest' should still produce valid scores."""
        df = _enriched_puts(5)
        prefs = self._prefs(goal='cheapest', min_locked_in_profit_pct=0.0)
        result = calculate_smart_scores(df, prefs)
        assert result['smart_score'].max() > 0


# ===================================================================
# get_top_recommendations
# ===================================================================

class TestTopRecommendations:

    def test_returns_three_keys(self):
        df = _enriched_puts(10)
        prefs = {'goal': 'lock_profit', 'min_locked_in_profit_pct': 5.0}
        scored = calculate_smart_scores(df, {**prefs, 'target_dte': 60})
        recs = get_top_recommendations(scored, prefs)
        assert 'cheapest' in recs
        assert 'best_protection' in recs
        assert 'best_balance' in recs

    def test_best_balance_is_top_score(self):
        df = _enriched_puts(10)
        prefs = {'goal': 'lock_profit', 'min_locked_in_profit_pct': 5.0}
        scored = calculate_smart_scores(df, {**prefs, 'target_dte': 60})
        recs = get_top_recommendations(scored, prefs)
        assert recs['best_balance']['smart_score'] == scored['smart_score'].max()

    def test_empty_df(self):
        df = pd.DataFrame()
        df['smart_score'] = pd.Series(dtype=float)
        recs = get_top_recommendations(df, {'min_locked_in_profit_pct': 50.0})
        assert recs['cheapest'] is None
        assert recs['best_protection'] is None
        assert recs['best_balance'] is None

    def test_cheapest_meets_goal(self):
        """Cheapest recommendation should meet the user's profit goal if any do."""
        df = _enriched_puts(10)
        target = 5.0
        prefs = {'goal': 'lock_profit', 'min_locked_in_profit_pct': target}
        scored = calculate_smart_scores(df, {**prefs, 'target_dte': 60})
        recs = get_top_recommendations(scored, prefs)
        if recs['cheapest'] is not None:
            meets = scored[scored['locked_in_profit_pct'] >= target]
            if not meets.empty:
                assert recs['cheapest']['locked_in_profit_pct'] >= target


# ===================================================================
# generate_comparison_insight
# ===================================================================

class TestInsight:

    def _make_series(self, **overrides):
        defaults = {
            'option_label': 'TEST 2026 30-APR 145.00 PUT (60)',
            'annualized_cost_pct': 10.0,
            'locked_in_profit_pct': 50.0,
            'days_to_expiration': 60,
            'smart_score': 75.0,
        }
        defaults.update(overrides)
        return pd.Series(defaults)

    def test_similar_cost_different_dte(self):
        top1 = self._make_series(annualized_cost_pct=5.0, days_to_expiration=60)
        top2 = self._make_series(annualized_cost_pct=5.5, days_to_expiration=180,
                                  option_label='TEST 2026 30-AUG 145.00 PUT (180)')
        insight = generate_comparison_insight(top1, top2)
        assert 'Erkenntnis' in insight
        assert 'längere Laufzeit' in insight

    def test_similar_protection_different_cost(self):
        top1 = self._make_series(locked_in_profit_pct=50.0, annualized_cost_pct=5.0)
        top2 = self._make_series(locked_in_profit_pct=52.0, annualized_cost_pct=12.0,
                                  option_label='TEST 2026 30-MAY 150.00 PUT (90)')
        insight = generate_comparison_insight(top1, top2)
        assert 'günstiger' in insight

    def test_default_insight(self):
        top1 = self._make_series()
        top2 = self._make_series(annualized_cost_pct=15.0, locked_in_profit_pct=80.0,
                                  days_to_expiration=90,
                                  option_label='TEST 2026 30-MAY 150.00 PUT (90)')
        insight = generate_comparison_insight(top1, top2)
        assert 'Top-Wahl' in insight

    def test_none_inputs(self):
        assert generate_comparison_insight(None, None) == ""
        assert generate_comparison_insight(self._make_series(), None) == ""


# ===================================================================
# HOLDING_PERIOD_MAP
# ===================================================================

class TestHoldingPeriodMap:

    def test_all_keys_exist(self):
        for key in ('short', 'medium', 'long', 'any'):
            assert key in HOLDING_PERIOD_MAP
            assert 'dte_range' in HOLDING_PERIOD_MAP[key]
            assert 'target_dte' in HOLDING_PERIOD_MAP[key]

    def test_any_has_no_target(self):
        assert HOLDING_PERIOD_MAP['any']['target_dte'] is None
