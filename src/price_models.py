"""
Stochastic price / volatility models for the Monte Carlo simulator.

Public API
----------
- PriceModel        : abstract base class
- GBMModel          : geometric Brownian motion with constant sigma (baseline)
- HestonModel       : stochastic volatility with mean-reverting variance
                      (full-truncation Euler scheme on dv = kappa(theta-v) dt + xi sqrt(v) dW)
- IVShockModel      : GBM for the underlying + simple deterministic IV
                      mean-reversion (exponential decay to long-run mean)

Each model yields, for `simulate_price_paths`, a tuple `(S, sigma)` with shapes:
    S     : (num_simulations, n_steps + 1)   underlying paths
    sigma : (num_simulations, n_steps + 1)   instantaneous volatility per step
                                              (constant column for GBM,
                                               stochastic for Heston / IVShock)

Notes
-----
- The "sigma" returned is the *spot* (instantaneous) volatility used at each step
  to re-price options via Black-Scholes within the management loop.
- For the terminal-only path (no management), only `simulate_terminal_prices`
  is needed; for stochastic-vol models we still integrate the full path.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple

import numpy as np

DAYS_PER_YEAR = 365


# --------------------------------------------------------------------------- #
#  Base                                                                       #
# --------------------------------------------------------------------------- #
class PriceModel(ABC):
    """Abstract base class for joint underlying / volatility models."""

    @abstractmethod
    def simulate_terminal_prices(self, num_simulations: int,
                                 dte: int, seed: int) -> np.ndarray: ...

    @abstractmethod
    def simulate_price_paths(self, num_simulations: int,
                             dte: int, seed: int
                             ) -> Tuple[np.ndarray, np.ndarray]: ...

    @abstractmethod
    def cache_signature(self) -> tuple:
        """Hashable signature of the model for cache keys."""


# --------------------------------------------------------------------------- #
#  GBM                                                                        #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class GBMModel(PriceModel):
    """Constant-sigma geometric Brownian motion."""
    s0: float
    sigma: float
    risk_free_rate: float = 0.03
    dividend_yield: float = 0.0

    def simulate_terminal_prices(self, num_simulations: int,
                                 dte: int, seed: int) -> np.ndarray:
        if dte == 0:
            return np.full(num_simulations, self.s0)
        T = dte / DAYS_PER_YEAR
        drift = (self.risk_free_rate - self.dividend_yield
                 - 0.5 * self.sigma ** 2) * T
        shock = (self.sigma * np.sqrt(T)
                 * np.random.default_rng(seed).standard_normal(num_simulations))
        return self.s0 * np.exp(drift + shock)

    def simulate_price_paths(self, num_simulations: int,
                             dte: int, seed: int
                             ) -> Tuple[np.ndarray, np.ndarray]:
        N = num_simulations
        if dte == 0:
            S = np.full((N, 1), self.s0)
            sig = np.full((N, 1), self.sigma)
            return S, sig
        dt = 1.0 / DAYS_PER_YEAR
        drift = (self.risk_free_rate - self.dividend_yield
                 - 0.5 * self.sigma ** 2) * dt
        vol_step = self.sigma * np.sqrt(dt)
        rng = np.random.default_rng(seed)
        Z = rng.standard_normal((N, dte))
        log_inc = drift + vol_step * Z
        log_paths = np.empty((N, dte + 1))
        log_paths[:, 0] = 0.0
        np.cumsum(log_inc, axis=1, out=log_paths[:, 1:])
        S = self.s0 * np.exp(log_paths)
        sig = np.full((N, dte + 1), self.sigma)
        return S, sig

    def cache_signature(self) -> tuple:
        return ("GBM", self.s0, self.sigma,
                self.risk_free_rate, self.dividend_yield)


# --------------------------------------------------------------------------- #
#  Heston                                                                     #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class HestonModel(PriceModel):
    """
    Heston stochastic-volatility model, simulated with full-truncation Euler.

        dS = (r - q) S dt + sqrt(v) S dW^S
        dv = kappa (theta - v) dt + xi sqrt(v) dW^v
        d<W^S, W^v> = rho dt

    Parameters
    ----------
    s0       : initial spot
    v0       : initial variance (sigma_0 ** 2)
    kappa    : mean-reversion speed (literature default ~ 2.0)
    theta    : long-run variance (long_run_iv ** 2)
    xi       : vol-of-vol  (~ 0.3)
    rho      : correlation between dW^S and dW^v (~ -0.7)
    """
    s0: float
    v0: float
    kappa: float = 2.0
    theta: float = 0.04
    xi: float = 0.3
    rho: float = -0.7
    risk_free_rate: float = 0.03
    dividend_yield: float = 0.0

    def simulate_terminal_prices(self, num_simulations: int,
                                 dte: int, seed: int) -> np.ndarray:
        S, _ = self.simulate_price_paths(num_simulations, dte, seed)
        return S[:, -1]

    def simulate_price_paths(self, num_simulations: int,
                             dte: int, seed: int
                             ) -> Tuple[np.ndarray, np.ndarray]:
        N = num_simulations
        if dte == 0:
            S = np.full((N, 1), self.s0)
            sig = np.full((N, 1), np.sqrt(max(self.v0, 0.0)))
            return S, sig

        dt = 1.0 / DAYS_PER_YEAR
        rng = np.random.default_rng(seed)
        Z1 = rng.standard_normal((N, dte))
        Z2 = rng.standard_normal((N, dte))
        # correlated Brownian increments
        dW_v = Z1
        dW_s = self.rho * Z1 + np.sqrt(max(1.0 - self.rho ** 2, 0.0)) * Z2

        S = np.empty((N, dte + 1))
        v = np.empty((N, dte + 1))
        S[:, 0] = self.s0
        v[:, 0] = max(self.v0, 0.0)

        sqrt_dt = np.sqrt(dt)
        for t in range(dte):
            v_pos = np.maximum(v[:, t], 0.0)            # full truncation
            sqrt_v = np.sqrt(v_pos)
            v[:, t + 1] = (v[:, t]
                           + self.kappa * (self.theta - v_pos) * dt
                           + self.xi * sqrt_v * sqrt_dt * dW_v[:, t])
            S[:, t + 1] = S[:, t] * np.exp(
                (self.risk_free_rate - self.dividend_yield - 0.5 * v_pos) * dt
                + sqrt_v * sqrt_dt * dW_s[:, t]
            )
        sig = np.sqrt(np.maximum(v, 0.0))
        return S, sig

    def cache_signature(self) -> tuple:
        return ("Heston", self.s0, self.v0, self.kappa, self.theta,
                self.xi, self.rho, self.risk_free_rate, self.dividend_yield)


# --------------------------------------------------------------------------- #
#  IV-Shock (deterministic IV mean reversion + GBM underlying)                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IVShockModel(PriceModel):
    """
    Simple, deterministic IV mean-reversion combined with GBM underlying.

    The volatility used to *simulate the underlying* at each step is
    `sigma(t) = lr_iv + (iv0 - lr_iv) * exp(-ln(2) * t / half_life_days)`,
    i.e. an exponential decay from the (potentially shocked) initial IV
    `iv0` to the long-run mean `lr_iv` with the given half-life.

    This is intentionally minimal, but it captures Tasty-style "vol crush":
    when iv0 > lr_iv, short-premium positions de-value faster than pure
    Theta would predict, so TP triggers earlier in the managed loop.
    """
    s0: float
    iv0: float                  # initial implied vol (e.g. 0.45 after a spike)
    lr_iv: float = 0.20         # long-run mean implied vol
    half_life_days: float = 10.0
    risk_free_rate: float = 0.03
    dividend_yield: float = 0.0

    def _sigma_curve(self, n_steps_plus_one: int) -> np.ndarray:
        """sigma per day for steps 0..dte (deterministic)."""
        t = np.arange(n_steps_plus_one)
        decay = np.exp(-np.log(2.0) * t / max(self.half_life_days, 1e-9))
        return self.lr_iv + (self.iv0 - self.lr_iv) * decay

    def simulate_terminal_prices(self, num_simulations: int,
                                 dte: int, seed: int) -> np.ndarray:
        S, _ = self.simulate_price_paths(num_simulations, dte, seed)
        return S[:, -1]

    def simulate_price_paths(self, num_simulations: int,
                             dte: int, seed: int
                             ) -> Tuple[np.ndarray, np.ndarray]:
        N = num_simulations
        if dte == 0:
            S = np.full((N, 1), self.s0)
            sig = np.full((N, 1), self.iv0)
            return S, sig

        dt = 1.0 / DAYS_PER_YEAR
        sigma_curve = self._sigma_curve(dte + 1)        # (dte+1,)
        # Use the per-step sigma at the START of each interval to drive returns
        step_sigma = sigma_curve[:-1]                   # (dte,)
        drift = ((self.risk_free_rate - self.dividend_yield
                  - 0.5 * step_sigma ** 2) * dt)        # (dte,)
        vol_step = step_sigma * np.sqrt(dt)             # (dte,)

        rng = np.random.default_rng(seed)
        Z = rng.standard_normal((N, dte))
        log_inc = drift[None, :] + vol_step[None, :] * Z
        log_paths = np.empty((N, dte + 1))
        log_paths[:, 0] = 0.0
        np.cumsum(log_inc, axis=1, out=log_paths[:, 1:])
        S = self.s0 * np.exp(log_paths)
        sig = np.broadcast_to(sigma_curve[None, :], (N, dte + 1)).copy()
        return S, sig

    def cache_signature(self) -> tuple:
        return ("IVShock", self.s0, self.iv0, self.lr_iv,
                self.half_life_days, self.risk_free_rate, self.dividend_yield)
