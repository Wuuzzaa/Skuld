"""Tests for the stochastic price/volatility models in src.price_models."""
import numpy as np
import pytest

from src.price_models import GBMModel, HestonModel, IVShockModel


def test_gbm_terminal_lognormal_mean():
    """GBM terminal mean E[S_T] ~ S0 * exp((r - q) * T) (risk-neutral drift)."""
    model = GBMModel(s0=100.0, sigma=0.30, risk_free_rate=0.03, dividend_yield=0.0)
    ST = model.simulate_terminal_prices(num_simulations=200_000, dte=45, seed=42)
    expected = 100.0 * np.exp(0.03 * 45 / 365)
    assert ST.shape == (200_000,)
    assert ST.min() > 0
    assert abs(ST.mean() - expected) / expected < 0.01


def test_gbm_paths_shape_and_sigma():
    model = GBMModel(s0=100.0, sigma=0.25)
    S, sig = model.simulate_price_paths(num_simulations=1000, dte=30, seed=1)
    assert S.shape == (1000, 31)
    assert sig.shape == (1000, 31)
    assert np.allclose(sig, 0.25)


def test_heston_variance_mean_reverts():
    """Heston variance must mean-revert towards theta over a long horizon."""
    long_run_var = 0.04
    model = HestonModel(
        s0=100.0, v0=0.16, kappa=4.0, theta=long_run_var,
        xi=0.3, rho=-0.7,
    )
    S, sig = model.simulate_price_paths(num_simulations=5_000, dte=365, seed=7)
    var_paths = sig ** 2
    # variance at the end should be much closer to theta than v0 was
    end_mean = var_paths[:, -1].mean()
    assert abs(end_mean - long_run_var) < abs(0.16 - long_run_var)


def test_heston_zero_xi_matches_gbm_drift():
    """xi=0 collapses the variance SDE to deterministic decay; means should match GBM."""
    sigma_const = 0.20
    heston = HestonModel(s0=100.0, v0=sigma_const ** 2, kappa=0.0,
                         theta=sigma_const ** 2, xi=0.0, rho=0.0)
    gbm = GBMModel(s0=100.0, sigma=sigma_const)
    ST_h = heston.simulate_terminal_prices(50_000, 60, seed=11)
    ST_g = gbm.simulate_terminal_prices(50_000, 60, seed=11)
    # both are risk-neutral; sample means must be close
    assert abs(ST_h.mean() - ST_g.mean()) / ST_g.mean() < 0.02


def test_iv_shock_decays_to_long_run():
    """IVShockModel sigma must converge towards lr_iv."""
    model = IVShockModel(s0=100.0, iv0=0.60, lr_iv=0.20, half_life_days=10.0)
    _, sig = model.simulate_price_paths(num_simulations=10, dte=120, seed=0)
    # all sims share the deterministic curve
    assert np.allclose(sig[0], sig[1])
    assert sig[0, 0] == pytest.approx(0.60, rel=1e-6)
    # after several half-lives sigma should be very close to lr_iv
    assert abs(sig[0, -1] - 0.20) < 1e-3
    # half-life check (10 days)
    assert sig[0, 10] == pytest.approx(0.20 + 0.40 * 0.5, rel=1e-3)


def test_cache_signatures_distinct():
    a = GBMModel(s0=100, sigma=0.2).cache_signature()
    b = HestonModel(s0=100, v0=0.04).cache_signature()
    c = IVShockModel(s0=100, iv0=0.4, lr_iv=0.2).cache_signature()
    assert len({a, b, c}) == 3
