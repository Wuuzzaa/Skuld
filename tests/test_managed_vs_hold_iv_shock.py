"""
Validates that under an IV-shock vol model (Tasty narrative: vol-crush), the
managed variant (TP 50 / SL 200 / DTE close 21) reaches a HIGHER raw EV than
hold-to-expiration on a 45-DTE iron condor opened at iv0 well above lr_iv.
"""
import pytest

from src.monte_carlo_simulation import (
    MonteCarloSimulator, OptionLeg, ManagementConfig,
)
from src.price_models import IVShockModel


@pytest.fixture(scope="module")
def iron_condor():
    return [
        OptionLeg(strike=335.0, premium=4.65, is_call=False, is_long=True,  iv=0.45, delta=-0.15, gamma=0.01, vega=0.5, theta=0.1),
        OptionLeg(strike=340.0, premium=5.51, is_call=False, is_long=False, iv=0.44, delta=-0.20, gamma=0.012, vega=0.55, theta=0.12),
        OptionLeg(strike=465.0, premium=4.85, is_call=True,  is_long=False, iv=0.35, delta=0.18, gamma=0.011, vega=0.52, theta=0.11),
        OptionLeg(strike=470.0, premium=4.20, is_call=True,  is_long=True,  iv=0.34, delta=0.14, gamma=0.009, vega=0.48, theta=0.09),
    ]


def _build_sim(price_model):
    return MonteCarloSimulator(
        current_price=395.09, volatility=0.43, dte=45,
        num_simulations=20_000, iv_correction=0,
        price_model=price_model, random_seed=123,
    )


def test_managed_beats_hold_under_vol_crush(iron_condor):
    model = IVShockModel(s0=395.09, iv0=0.43, lr_iv=0.20, half_life_days=10.0)
    sim = _build_sim(model)

    mgmt = ManagementConfig(tp_pct=50.0, sl_pct=200.0, dte_close=21)
    a = sim.analyze_strategy(iron_condor, management=mgmt, with_greeks=False)
    b = sim.analyze_strategy(iron_condor, management=None, with_greeks=False)

    # Under vol-crush, managed should have a *higher* raw EV than hold.
    assert a.expected_value > b.expected_value
    # Sanity: managed must have *lower* tail risk (less negative max loss).
    assert a.max_loss > b.max_loss


def test_no_management_returns_no_management_stats(iron_condor):
    sim = _build_sim(None)
    res = sim.analyze_strategy(iron_condor, management=None, with_greeks=False)
    assert res.management_stats is None
    assert res.extras["pnl"].shape[0] == sim.num_simulations
