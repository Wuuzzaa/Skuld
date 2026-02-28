"""
Tests for src/call_income_simulator.py
"""

import unittest
from datetime import date

import pandas as pd

from src.call_income_simulator import (
    MonthlyCall,
    SimulationResult,
    build_auto_call_plan,
    calculate_assignment_scenario,
    calculate_months_to_breakeven,
    find_otm_call_strike,
    simulate_call_income,
    _get_month_status,
)


# ── Helpers ─────────────────────────────────────────────────────────

def _make_call(month_label="2026-03 (März)", exp=date(2026, 3, 20),
               strike=143.0, premium=3.20, dte=20, oi=500) -> MonthlyCall:
    return MonthlyCall(
        month_label=month_label,
        expiration_date=exp,
        strike=strike,
        premium=premium,
        days_to_expiration=dte,
        open_interest=oi,
    )


def _make_calls_df(strikes=None, expirations=None, premiums=None):
    """Build a simple calls DataFrame for testing build_auto_call_plan."""
    strikes = strikes or [140.0, 143.0, 145.0, 150.0]
    expirations = expirations or [date(2026, 3, 20)]
    premiums = premiums or {140.0: 5.0, 143.0: 3.2, 145.0: 2.5, 150.0: 1.5}

    rows = []
    for exp in expirations:
        dte = (exp - date.today()).days
        for s in strikes:
            rows.append({
                "strike_price": s,
                "option_price": premiums.get(s, 2.0),
                "expiration_date": pd.Timestamp(exp),
                "days_to_expiration": max(dte, 1),
                "open_interest": 100,
            })
    return pd.DataFrame(rows)


# =====================================================================
# Test: simulate_call_income
# =====================================================================
class TestSimulateCallIncome(unittest.TestCase):
    """Core simulation with spec testcase 2 values."""

    def setUp(self):
        self.call_plan = [
            _make_call("2026-03 (März)", date(2026, 3, 20), 143.0, 3.20, 20, 500),
            _make_call("2026-04 (April)", date(2026, 4, 17), 150.0, 2.80, 48, 300),
            _make_call("2026-05 (Mai)", date(2026, 5, 15), 135.0, 7.10, 76, 200),
        ]
        self.result = simulate_call_income(
            symbol="PLTR",
            cost_basis=35.0,
            current_price=130.30,
            put_strike=120.0,
            put_price=8.0,
            put_expiration_date=date(2026, 8, 21),
            call_plan=self.call_plan,
        )

    def test_total_call_income(self):
        self.assertAlmostEqual(self.result.total_call_income, 13.10, places=2)

    def test_net_insurance_cost(self):
        # 8 - 13.10 = -5.10 (Credit)
        self.assertAlmostEqual(self.result.net_insurance_cost, -5.10, places=2)

    def test_put_cost_covered_pct(self):
        # 13.10 / 8 * 100 = 163.75
        self.assertAlmostEqual(self.result.put_cost_covered_pct, 163.75, places=2)

    def test_months_to_breakeven(self):
        # cumulative: 3.20, 6.00, 13.10 → breakeven at month 3
        self.assertEqual(self.result.months_to_breakeven, 3)

    def test_effective_cost_basis(self):
        # 35 + 8 - 13.10 = 29.90
        self.assertAlmostEqual(self.result.effective_cost_basis, 29.90, places=2)

    def test_effective_locked_in_profit(self):
        # 120 - 29.90 = 90.10
        self.assertAlmostEqual(self.result.effective_locked_in_profit, 90.10, places=2)

    def test_effective_locked_in_profit_pct(self):
        # 90.10 / 29.90 * 100 ≈ 301.34
        self.assertAlmostEqual(self.result.effective_locked_in_profit_pct, 301.34, places=1)

    def test_avg_monthly_income(self):
        # 13.10 / 3 ≈ 4.367
        self.assertAlmostEqual(self.result.avg_monthly_income, 4.367, places=2)

    def test_monthly_details_count(self):
        self.assertEqual(len(self.result.monthly_details), 3)

    def test_monthly_status_sequence(self):
        statuses = [d["status"] for d in self.result.monthly_details]
        self.assertEqual(statuses[0], "⏳ Offen")
        self.assertEqual(statuses[1], "⏳ Offen")
        self.assertEqual(statuses[2], "✅ Breakeven!")

    def test_cumulative_values(self):
        cums = [d["cumulative"] for d in self.result.monthly_details]
        self.assertAlmostEqual(cums[0], 3.20, places=2)
        self.assertAlmostEqual(cums[1], 6.00, places=2)
        self.assertAlmostEqual(cums[2], 13.10, places=2)


# =====================================================================
# Test: empty call plan
# =====================================================================
class TestEmptyCallPlan(unittest.TestCase):

    def test_empty_plan_returns_zero(self):
        result = simulate_call_income(
            symbol="TEST", cost_basis=50.0, current_price=100.0,
            put_strike=90.0, put_price=5.0,
            put_expiration_date=date(2026, 12, 31),
            call_plan=[],
        )
        self.assertEqual(result.total_call_income, 0.0)
        self.assertEqual(result.net_insurance_cost, 5.0)
        self.assertIsNone(result.months_to_breakeven)
        self.assertEqual(result.effective_cost_basis, 55.0)
        self.assertEqual(len(result.monthly_details), 0)


# =====================================================================
# Test: breakeven not reached
# =====================================================================
class TestBreakevenNotReached(unittest.TestCase):

    def test_expensive_put(self):
        """Spec testcase 3: put $25, 3 months × ~$3 = $9."""
        plan = [
            _make_call(premium=3.0),
            _make_call(premium=3.0, month_label="2026-04", exp=date(2026, 4, 17)),
            _make_call(premium=3.0, month_label="2026-05", exp=date(2026, 5, 15)),
        ]
        result = simulate_call_income(
            symbol="TEST", cost_basis=50.0, current_price=100.0,
            put_strike=90.0, put_price=25.0,
            put_expiration_date=date(2026, 8, 21),
            call_plan=plan,
        )
        self.assertAlmostEqual(result.total_call_income, 9.0)
        self.assertAlmostEqual(result.net_insurance_cost, 16.0)
        self.assertAlmostEqual(result.put_cost_covered_pct, 36.0)
        self.assertIsNone(result.months_to_breakeven)


# =====================================================================
# Test: calculate_months_to_breakeven
# =====================================================================
class TestMonthsToBreakeven(unittest.TestCase):

    def test_exact_breakeven_first_month(self):
        plan = [_make_call(premium=8.0)]
        self.assertEqual(calculate_months_to_breakeven(8.0, plan), 1)

    def test_over_breakeven_second_month(self):
        plan = [_make_call(premium=5.0), _make_call(premium=5.0)]
        self.assertEqual(calculate_months_to_breakeven(8.0, plan), 2)

    def test_not_reached(self):
        plan = [_make_call(premium=1.0), _make_call(premium=1.0)]
        self.assertIsNone(calculate_months_to_breakeven(8.0, plan))

    def test_empty_plan(self):
        self.assertIsNone(calculate_months_to_breakeven(8.0, []))


# =====================================================================
# Test: find_otm_call_strike
# =====================================================================
class TestFindOTMCallStrike(unittest.TestCase):

    def test_exact_match(self):
        strikes = [130.0, 135.0, 140.0, 145.0, 150.0]
        # 130 * 1.10 = 143 → nearest >= 143 = 145
        self.assertEqual(find_otm_call_strike(strikes, 130.0, 10.0), 145.0)

    def test_atm(self):
        strikes = [130.0, 135.0, 140.0]
        # 0% OTM → target = 130 → nearest >= 130 = 130
        self.assertEqual(find_otm_call_strike(strikes, 130.0, 0.0), 130.0)

    def test_fallback_highest(self):
        strikes = [130.0, 135.0]
        # 130 * 1.50 = 195 → no candidates → fallback to max = 135
        self.assertEqual(find_otm_call_strike(strikes, 130.0, 50.0), 135.0)

    def test_empty_list(self):
        self.assertIsNone(find_otm_call_strike([], 100.0, 10.0))

    def test_5_pct_otm(self):
        strikes = [136.0, 137.0, 140.0]
        # 130 * 1.05 = 136.5 → nearest >= 136.5 = 137
        self.assertEqual(find_otm_call_strike(strikes, 130.0, 5.0), 137.0)


# =====================================================================
# Test: build_auto_call_plan
# =====================================================================
class TestBuildAutoCallPlan(unittest.TestCase):

    def test_basic_plan(self):
        df = _make_calls_df(
            strikes=[140.0, 143.0, 145.0, 150.0],
            expirations=[date(2026, 3, 20), date(2026, 4, 17), date(2026, 5, 15)],
            premiums={140.0: 5.0, 143.0: 3.2, 145.0: 2.5, 150.0: 1.5},
        )
        plan = build_auto_call_plan(
            current_price=130.0,
            put_expiration_date=date(2026, 8, 21),
            otm_pct=10.0,  # target = 143 → 143.0
            calls_df=df,
        )
        self.assertEqual(len(plan), 3)
        # All should pick 143 strike (130 * 1.10 = 143, exact match)
        for c in plan:
            self.assertEqual(c.strike, 143.0)

    def test_excludes_put_expiry_month(self):
        df = _make_calls_df(
            expirations=[date(2026, 8, 15)],  # in the put-expiry month
        )
        plan = build_auto_call_plan(
            current_price=130.0,
            put_expiration_date=date(2026, 8, 21),
            otm_pct=5.0,
            calls_df=df,
        )
        # Aug 15 < Aug 21, so it should be included
        self.assertEqual(len(plan), 1)

    def test_excludes_after_put_expiry(self):
        df = _make_calls_df(
            expirations=[date(2026, 9, 18)],  # after put expiry
        )
        plan = build_auto_call_plan(
            current_price=130.0,
            put_expiration_date=date(2026, 8, 21),
            otm_pct=5.0,
            calls_df=df,
        )
        self.assertEqual(len(plan), 0)

    def test_empty_df(self):
        plan = build_auto_call_plan(130.0, date(2026, 8, 21), 10.0, pd.DataFrame())
        self.assertEqual(len(plan), 0)

    def test_none_df(self):
        plan = build_auto_call_plan(130.0, date(2026, 8, 21), 10.0, None)
        self.assertEqual(len(plan), 0)

    def test_sorted_by_expiration(self):
        df = _make_calls_df(
            expirations=[date(2026, 5, 15), date(2026, 3, 20), date(2026, 4, 17)],
        )
        plan = build_auto_call_plan(130.0, date(2026, 8, 21), 10.0, df)
        dates = [c.expiration_date for c in plan]
        self.assertEqual(dates, sorted(dates))


# =====================================================================
# Test: calculate_assignment_scenario
# =====================================================================
class TestAssignmentScenario(unittest.TestCase):

    def test_basic_assignment(self):
        call = _make_call(strike=143.0, premium=3.20)
        scenario = calculate_assignment_scenario(
            call=call,
            cost_basis=35.0,
            put_price=8.0,
            put_strike=120.0,
            cumulative_premiums_before=0.0,
        )
        # total_cost = 35 + 8 = 43
        self.assertAlmostEqual(scenario["total_cost"], 43.0)
        # call_credits = 0 + 3.20 = 3.20
        self.assertAlmostEqual(scenario["call_credits_so_far"], 3.20)
        # profit = 143 - 43 + 3.20 = 103.20
        self.assertAlmostEqual(scenario["profit_if_assigned"], 103.20)
        # put residual = max(0, 120 - 143) = 0
        self.assertAlmostEqual(scenario["put_residual_value"], 0.0)
        # total_return = 103.20 + 0 = 103.20
        self.assertAlmostEqual(scenario["total_return"], 103.20)

    def test_assignment_with_put_residual(self):
        """Call strike below put strike → put has residual value."""
        call = _make_call(strike=110.0, premium=8.0)
        scenario = calculate_assignment_scenario(
            call=call,
            cost_basis=35.0,
            put_price=8.0,
            put_strike=120.0,
            cumulative_premiums_before=5.0,
        )
        # total_cost = 43
        # call_credits = 5 + 8 = 13
        # profit = 110 - 43 + 13 = 80
        self.assertAlmostEqual(scenario["profit_if_assigned"], 80.0)
        # put residual = max(0, 120 - 110) = 10
        self.assertAlmostEqual(scenario["put_residual_value"], 10.0)
        # total_return = 80 + 10 = 90
        self.assertAlmostEqual(scenario["total_return"], 90.0)

    def test_total_return_pct(self):
        call = _make_call(strike=143.0, premium=3.20)
        scenario = calculate_assignment_scenario(
            call=call, cost_basis=35.0, put_price=8.0,
            put_strike=120.0, cumulative_premiums_before=0.0,
        )
        # 103.20 / 43 * 100 ≈ 240.0
        self.assertAlmostEqual(scenario["total_return_pct"], 240.0, places=0)


# =====================================================================
# Test: _get_month_status
# =====================================================================
class TestGetMonthStatus(unittest.TestCase):

    def test_open(self):
        self.assertEqual(_get_month_status(3.0, 8.0, False), "⏳ Offen")

    def test_breakeven(self):
        self.assertEqual(_get_month_status(8.0, 8.0, True), "✅ Breakeven!")

    def test_profit(self):
        self.assertEqual(_get_month_status(10.0, 8.0, False), "💰 Profit")


if __name__ == "__main__":
    unittest.main()
