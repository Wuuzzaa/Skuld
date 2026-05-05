"""
Universal Options Monte Carlo Simulator (clean rewrite).

Public API
----------
- OptionLeg              : dataclass for a single option leg
- ManagementConfig       : strategy-wide management rules (TP / SL / DTE-Close / Planned-DTE)
- StrategyAnalysis       : structured result of `analyze_strategy`
- MonteCarloSimulator    : the main engine

Conventions
-----------
- Strategy "value to close" (USD) = (sum_legs sign_long * BS_price) * 100 + spread_offset
  with sign_long = +1 for long legs, -1 for short legs.
- entry_value (USD, signed) = net cashflow at open
    + credit  (we receive money)  for net-short strategies
    - debit   (we pay money)      for net-long strategies
  Includes opening transaction costs.
- spread_offset = entry_value - entry_BS_value, applied to all subsequent BS valuations
  so day-0 valuation matches the actually paid/received premium.
- PnL on close: pnl = entry_value - close_value     (works for credit AND debit)
- TP/SL thresholds use |entry_value| as reference magnitude (matches TastyTrade-style
  "% of credit/debit" semantics for both directions).
- Trigger priority: DTE Close > TP > SL > Planned DTE.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from config import (
    IV_CORRECTION_MODE,
    NUM_SIMULATIONS,
    RANDOM_SEED,
    RISK_FREE_RATE,
    TRANSACTION_COST_PER_CONTRACT,
)
from src.decorator_log_function import log_function
from src.price_models import PriceModel

logger = logging.getLogger(__name__)

CONTRACT_MULTIPLIER = 100
DAYS_PER_YEAR = 365  # calendar-day convention (consistent with rest of code base)
MIN_IV = 0.01

# Exit reason codes
EXIT_EXPIRY = 0
EXIT_TP = 1
EXIT_SL = 2
EXIT_DTE = 3
EXIT_PLANNED = 4
EXIT_LABELS = {0: "expiry", 1: "tp", 2: "sl", 3: "dte_close", 4: "planned_dte"}


# --------------------------------------------------------------------------- #
#  Data model                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class OptionLeg:
    """A single option leg of a multi-leg strategy."""
    strike: float
    premium: float           # mid premium per share in USD (>= 0)
    is_call: bool
    is_long: bool
    delta: float
    gamma: float
    vega: float
    theta: float
    iv: float

    def __post_init__(self) -> None:
        if self.strike <= 0:
            raise ValueError(f"strike must be > 0, got {self.strike}")
        if self.premium < 0:
            raise ValueError(f"premium must be >= 0, got {self.premium}")



@dataclass(frozen=True)
class ManagementConfig:
    """
    Strategy-wide trade management. All values are optional;
    if every value is None the strategy is held to expiration.

    Parameters
    ----------
    tp_pct : float, optional
        Take profit threshold in percent of |entry_value|.
        Triggered when realized PnL >= tp_pct/100 * |entry_value|.
    sl_pct : float, optional
        Stop loss threshold in percent of |entry_value|.
        Triggered when realized PnL <= -sl_pct/100 * |entry_value|.
    dte_close : int, optional
        Close when remaining DTE drops to or below `dte_close`.
    planned_dte : int, optional
        Force close after `planned_dte` days since open (1-indexed).
    """
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    dte_close: Optional[int] = None
    planned_dte: Optional[int] = None

    @property
    def is_active(self) -> bool:
        return any(v is not None for v in (self.tp_pct, self.sl_pct,
                                           self.dte_close, self.planned_dte))


@dataclass
class StrategyAnalysis:
    """Structured result of `MonteCarloSimulator.analyze_strategy`."""
    expected_value: float
    expected_value_undiscounted: float
    entry_value: float                # signed: + credit / - debit
    spread_offset: float              # USD offset added to BS valuations
    win_probability: float
    loss_probability: float
    max_profit: float
    max_loss: float
    pnl_percentiles: Dict[int, float]
    breakevens: List[float]
    greeks: Dict[str, float]
    management_stats: Optional[Dict[str, float]] = None
    extras: Dict[str, np.ndarray] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Simulator                                                                  #
# --------------------------------------------------------------------------- #
class MonteCarloSimulator:
    """Monte-Carlo engine for arbitrary multi-leg option strategies."""

    # ---------- construction ---------------------------------------------- #
    def __init__(
        self,
        current_price: float,
        volatility: float,
        dte: int,
        risk_free_rate: float = RISK_FREE_RATE,
        dividend_yield: float = 0.0,
        num_simulations: int = NUM_SIMULATIONS,
        random_seed: int = RANDOM_SEED,
        transaction_cost_per_contract: float = TRANSACTION_COST_PER_CONTRACT,
        iv_correction: Union[str, float] = IV_CORRECTION_MODE,
        price_model: Optional[PriceModel] = None,
    ) -> None:
        if current_price <= 0:
            raise ValueError("current_price must be > 0")
        if volatility <= 0:
            raise ValueError("volatility must be > 0")
        if dte < 0:
            raise ValueError("dte must be >= 0")
        if num_simulations < 100:
            raise ValueError("num_simulations must be >= 100")

        self.current_price = float(current_price)
        self.raw_volatility = float(volatility)
        self.dte = int(dte)
        self.risk_free_rate = float(risk_free_rate)
        self.dividend_yield = float(dividend_yield)
        self.num_simulations = int(num_simulations)
        self.random_seed = int(random_seed)
        self.transaction_cost_per_contract = float(transaction_cost_per_contract)
        self.iv_correction = iv_correction
        self.price_model: Optional[PriceModel] = price_model

        self.time_to_expiration = self.dte / DAYS_PER_YEAR
        self.volatility, self.iv_correction_factor = self._apply_iv_correction(
            self.raw_volatility, self.dte, iv_correction
        )

        # local RNG -> no global seed pollution
        self._rng_seed = self.random_seed

        # caches: small dicts, separate for terminal-only vs. full paths
        self._terminal_cache: Dict[tuple, np.ndarray] = {}
        self._path_cache: Dict[tuple, np.ndarray] = {}
        self._path_sigma_cache: Dict[tuple, np.ndarray] = {}
        self._max_cache = 8

    def __repr__(self) -> str:
        return (f"MonteCarloSimulator(S={self.current_price}, "
                f"sigma={self.volatility:.4f}, dte={self.dte}, "
                f"N={self.num_simulations})")

    # ---------- IV correction --------------------------------------------- #
    @staticmethod
    def _auto_iv_correction_factor(dte: int) -> float:
        base = 0.08
        adj = 0.05 * np.log(max(dte, 1) / 30.0)
        return float(np.clip(base + adj, 0.08, 0.25))

    @classmethod
    def _apply_iv_correction(
        cls, market_iv: float, dte: int, mode: Union[str, float]
    ) -> Tuple[float, float]:
        if isinstance(mode, str):
            key = mode.lower()
            if key == "none":
                factor = 0.0
            elif key == "auto":
                factor = cls._auto_iv_correction_factor(dte)
            else:
                raise ValueError(f"Invalid iv_correction string: {mode!r}")
        else:
            factor = float(mode)
            if not 0.0 <= factor <= 1.0:
                raise ValueError("iv_correction float must be in [0.0, 1.0]")
        corrected = max(market_iv * (1.0 - factor), MIN_IV)
        return corrected, factor

    # ---------- price simulation ------------------------------------------ #
    def _cache_key(self) -> tuple:
        model_sig = self.price_model.cache_signature() if self.price_model else \
            ("GBM", self.current_price, self.volatility,
             self.risk_free_rate, self.dividend_yield)
        return (model_sig, self.dte, self.num_simulations, self._rng_seed)

    def _path_sigma(self) -> Optional[np.ndarray]:
        """Per-step sigma matrix (N, dte+1) if a price model was supplied."""
        return self._path_sigma_cache.get(self._cache_key())

    def simulate_terminal_prices(self) -> np.ndarray:
        """Terminal prices ST. O(N) for GBM, O(N*dte) for stochastic-vol models."""
        key = self._cache_key()
        cached = self._terminal_cache.get(key)
        if cached is not None:
            return cached

        if self.price_model is not None:
            st = self.price_model.simulate_terminal_prices(
                self.num_simulations, self.dte, self._rng_seed
            )
        elif self.dte == 0:
            st = np.full(self.num_simulations, self.current_price)
        else:
            T = self.time_to_expiration
            sigma = self.volatility
            drift = (self.risk_free_rate - self.dividend_yield
                     - 0.5 * sigma ** 2) * T
            shock = (sigma * np.sqrt(T)
                     * np.random.default_rng(self._rng_seed)
                     .standard_normal(self.num_simulations))
            st = self.current_price * np.exp(drift + shock)
        self._store(self._terminal_cache, key, st)
        return st

    def simulate_price_paths(self) -> np.ndarray:
        """Full daily price paths, shape (num_simulations, dte+1)."""
        key = self._cache_key()
        cached = self._path_cache.get(key)
        if cached is not None:
            return cached

        if self.price_model is not None:
            paths, sigma_paths = self.price_model.simulate_price_paths(
                self.num_simulations, self.dte, self._rng_seed
            )
            self._store(self._path_sigma_cache, key, sigma_paths)
        else:
            N, T = self.num_simulations, self.dte
            if T == 0:
                paths = np.full((N, 1), self.current_price)
            else:
                dt = 1.0 / DAYS_PER_YEAR
                sigma = self.volatility
                drift = (self.risk_free_rate - self.dividend_yield
                         - 0.5 * sigma ** 2) * dt
                vol_step = sigma * np.sqrt(dt)
                rng = np.random.default_rng(self._rng_seed)
                Z = rng.standard_normal((N, T))
                log_increments = drift + vol_step * Z
                log_paths = np.empty((N, T + 1))
                log_paths[:, 0] = 0.0
                np.cumsum(log_increments, axis=1, out=log_paths[:, 1:])
                paths = self.current_price * np.exp(log_paths)
        self._store(self._path_cache, key, paths)
        return paths

    def _store(self, cache: dict, key: tuple, value: np.ndarray) -> None:
        if len(cache) >= self._max_cache:
            cache.pop(next(iter(cache)))
        cache[key] = value

    # ---------- pricing --------------------------------------------------- #
    @staticmethod
    def _fast_norm_cdf(x: np.ndarray) -> np.ndarray:
        """Abramowitz & Stegun 5-term approximation, max abs error ~7.5e-8."""
        a1, a2, a3 = 0.254829592, -0.284496736, 1.421413741
        a4, a5, p = -1.453152027, 1.061405429, 0.3275911
        sign = np.sign(x)
        ax = np.abs(x) / np.sqrt(2.0)
        t = 1.0 / (1.0 + p * ax)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) \
            * t * np.exp(-ax * ax)
        return 0.5 * (1.0 + sign * y)

    @classmethod
    def _black_scholes(
        cls,
        S: np.ndarray, K: np.ndarray, T: np.ndarray,
        r: float, sigma: float, is_call: np.ndarray,
    ) -> np.ndarray:
        """Vectorised Black-Scholes price per share (no dividend yield here)."""
        S = np.asarray(S, dtype=float)
        K = np.asarray(K, dtype=float)
        T = np.asarray(T, dtype=float)
        is_call = np.asarray(is_call, dtype=bool)

        intrinsic = np.where(
            is_call,
            np.maximum(S - K, 0.0),
            np.maximum(K - S, 0.0),
        )
        T_safe = np.where(T > 0, T, 1.0)
        sqrtT = np.sqrt(T_safe)
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T_safe) / (sigma * sqrtT)
        d2 = d1 - sigma * sqrtT
        Nd1 = cls._fast_norm_cdf(d1)
        Nd2 = cls._fast_norm_cdf(d2)
        disc = np.exp(-r * T_safe)
        call = S * Nd1 - K * disc * Nd2
        put = K * disc * (1.0 - Nd2) - S * (1.0 - Nd1)
        price = np.where(is_call, call, put)
        return np.where(T > 0, price, intrinsic)

    @classmethod
    def _black_scholes_path_sigma(
        cls,
        S: np.ndarray, K: np.ndarray, T: np.ndarray,
        r: float, sigma: np.ndarray, is_call: np.ndarray,
    ) -> np.ndarray:
        """Vectorised Black-Scholes with broadcastable per-element sigma."""
        S = np.asarray(S, dtype=float)
        K = np.asarray(K, dtype=float)
        T = np.asarray(T, dtype=float)
        sigma = np.maximum(np.asarray(sigma, dtype=float), MIN_IV)
        is_call = np.asarray(is_call, dtype=bool)

        intrinsic = np.where(
            is_call,
            np.maximum(S - K, 0.0),
            np.maximum(K - S, 0.0),
        )
        T_safe = np.where(T > 0, T, 1.0)
        sqrtT = np.sqrt(T_safe)
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T_safe) / (sigma * sqrtT)
        d2 = d1 - sigma * sqrtT
        Nd1 = cls._fast_norm_cdf(d1)
        Nd2 = cls._fast_norm_cdf(d2)
        disc = np.exp(-r * T_safe)
        call = S * Nd1 - K * disc * Nd2
        put = K * disc * (1.0 - Nd2) - S * (1.0 - Nd1)
        price = np.where(is_call, call, put)
        return np.where(T > 0, price, intrinsic)

    # ---------- strategy helpers ------------------------------------------ #
    @staticmethod
    def _legs_to_arrays(legs: Sequence[OptionLeg]) -> Dict[str, np.ndarray]:
        if not legs:
            raise ValueError("Strategy must contain at least one leg")
        return {
            "strikes":  np.array([l.strike for l in legs], dtype=float),
            "premiums": np.array([l.premium for l in legs], dtype=float),
            "is_call":  np.array([l.is_call for l in legs], dtype=bool),
            "is_long":  np.array([l.is_long for l in legs], dtype=bool),
            "ivs":      np.array([l.iv if l.iv is not None else np.nan for l in legs], dtype=float),
        }

    def _entry_cashflow(self, arr: Dict[str, np.ndarray]) -> float:
        """Net cashflow at open in USD (incl. opening transaction costs).

        + credit  (received) for net-short strategies
        - debit   (paid)     for net-long strategies
        """
        signs_pay = np.where(arr["is_long"], -1.0, 1.0)  # long pays, short receives
        net_premium = float(np.sum(signs_pay * arr["premiums"])) * CONTRACT_MULTIPLIER
        costs = self.transaction_cost_per_contract * len(arr["strikes"])
        return net_premium - costs

    def _entry_bs_value(self, arr: Dict[str, np.ndarray]) -> float:
        """Strategy value-to-close at t=0 from BS, USD (no spread offset)."""
        ivs = np.where(np.isnan(arr["ivs"]), self.volatility, arr["ivs"])
        bs0 = self._black_scholes_path_sigma(
            S=np.array([self.current_price]),
            K=arr["strikes"],
            T=np.array([self.time_to_expiration]),
            r=self.risk_free_rate, sigma=ivs,
            is_call=arr["is_call"],
        ).ravel()
        # Value to CLOSE: short legs cost money to buy back (-), long legs return money (+)
        signs = np.where(arr["is_long"], 1.0, -1.0)
        return float(np.sum(signs * bs0)) * CONTRACT_MULTIPLIER

    # ---------- terminal PnL (no management) ------------------------------ #
    def _terminal_pnl(
        self, legs: Sequence[OptionLeg]
    ) -> Tuple[np.ndarray, float, float]:
        arr = self._legs_to_arrays(legs)
        ST = self.simulate_terminal_prices()

        K = arr["strikes"][None, :]
        is_call = arr["is_call"][None, :]
        is_long = arr["is_long"][None, :]
        intrinsic = np.where(
            is_call,
            np.maximum(ST[:, None] - K, 0.0),
            np.maximum(K - ST[:, None], 0.0),
        )
        if self.price_model is not None:
            # Use BS-consistent entry valuation; PnL = entry_bs - terminal_intrinsic
            entry_bs = self._entry_bs_value(arr)
            entry_value = entry_bs
            spread_offset = 0.0
            terminal_strat_val = (
                np.where(is_long, intrinsic, -intrinsic).sum(axis=1)
                * CONTRACT_MULTIPLIER
            )
            costs = self.transaction_cost_per_contract * len(legs)
            total_pnl = entry_value - terminal_strat_val - costs
        else:
            long_pnl = (intrinsic - arr["premiums"][None, :]) * CONTRACT_MULTIPLIER
            short_pnl = (arr["premiums"][None, :] - intrinsic) * CONTRACT_MULTIPLIER
            leg_pnl = np.where(is_long, long_pnl, short_pnl)
            # symmetric with managed PnL: only opening transaction costs
            costs = self.transaction_cost_per_contract * len(legs)
            total_pnl = leg_pnl.sum(axis=1) - costs
            entry_value = self._entry_cashflow(arr)
            spread_offset = entry_value - self._entry_bs_value(arr)
        return total_pnl, entry_value, spread_offset

    # ---------- managed PnL ----------------------------------------------- #
    def _managed_pnl(
        self, legs: Sequence[OptionLeg], mgmt: ManagementConfig
    ) -> Tuple[np.ndarray, float, float, Dict[str, float]]:
        arr = self._legs_to_arrays(legs)
        N = self.num_simulations
        L = len(legs)

        paths = self.simulate_price_paths()         # (N, dte+1)
        sigma_paths = self._path_sigma()            # (N, dte+1) or None
        num_steps = paths.shape[1]
        days_remaining = self.dte - np.arange(num_steps)
        t_years = days_remaining / DAYS_PER_YEAR

        entry_value = self._entry_cashflow(arr)
        entry_bs = self._entry_bs_value(arr)
        # When a stochastic vol model is active the constant Day-0 market-vs-model
        # offset is not a meaningful "spread" any longer (sigma evolves, so the
        # gap is part of the model, not a static fee). Use offset only for GBM.
        if self.price_model is not None:
            spread_offset = 0.0
            entry_value = entry_bs   # PnL is measured purely on the BS valuation chain
        else:
            spread_offset = entry_value - entry_bs
        ref_magnitude = abs(entry_value)

        K = arr["strikes"]
        is_call = arr["is_call"]
        is_long = arr["is_long"]
        signs = np.where(is_long, 1.0, -1.0)

        active = np.ones(N, dtype=bool)
        exit_value = np.full(N, np.nan)
        exit_step = np.full(N, num_steps - 1, dtype=int)
        exit_reason = np.zeros(N, dtype=int)

        for step in range(1, num_steps):
            if not active.any():
                break
            T_left = t_years[step]

            if T_left <= 0:
                # use intrinsic value (no spread offset at expiry)
                S_active = paths[active, step]
                bs = np.where(
                    is_call[None, :],
                    np.maximum(S_active[:, None] - K[None, :], 0.0),
                    np.maximum(K[None, :] - S_active[:, None], 0.0),
                )
                strat_val = (bs * signs[None, :]).sum(axis=1) * CONTRACT_MULTIPLIER
            else:
                S_active = paths[active, step]
                S_grid = S_active[:, None]
                K_grid = np.broadcast_to(K[None, :], (S_active.size, L))
                T_grid = np.full_like(K_grid, T_left, dtype=float)
                isc_grid = np.broadcast_to(is_call[None, :], (S_active.size, L))
                if sigma_paths is not None:
                    # path-/time-dependent sigma: vectorise BS over (n_active, L)
                    sig_active = sigma_paths[active, step]            # (n_active,)
                    # Scale path sigma by the ratio of leg_iv to entry_volatility
                    # to maintain the skew/smile relative to the moving spot sigma.
                    leg_ivs = np.where(np.isnan(arr["ivs"]), self.volatility, arr["ivs"])
                    skew_ratio = leg_ivs / self.volatility
                    sig_grid = sig_active[:, None] * skew_ratio[None, :]
                    bs = self._black_scholes_path_sigma(
                        S_grid, K_grid, T_grid,
                        self.risk_free_rate,
                        sig_grid, isc_grid,
                    )
                else:
                    # Constant GBM: use per-leg IV if available
                    leg_ivs = np.where(np.isnan(arr["ivs"]), self.volatility, arr["ivs"])
                    bs = self._black_scholes_path_sigma(
                        S_grid, K_grid, T_grid,
                        self.risk_free_rate, leg_ivs[None, :], isc_grid,
                    )
                strat_val = ((bs * signs[None, :]).sum(axis=1)
                             * CONTRACT_MULTIPLIER + spread_offset)

            pnl_now = entry_value - strat_val

            trig_dte = (mgmt.dte_close is not None
                        and days_remaining[step] <= mgmt.dte_close)
            trig_planned = (mgmt.planned_dte is not None
                            and step >= mgmt.planned_dte)

            reason_local = np.zeros_like(strat_val, dtype=int)
            if trig_planned:
                reason_local[:] = EXIT_PLANNED
            if mgmt.sl_pct is not None and ref_magnitude > 0:
                sl_mask = pnl_now <= -(mgmt.sl_pct / 100.0) * ref_magnitude
                reason_local = np.where(sl_mask, EXIT_SL, reason_local)
            if mgmt.tp_pct is not None and ref_magnitude > 0:
                tp_mask = pnl_now >= (mgmt.tp_pct / 100.0) * ref_magnitude
                reason_local = np.where(tp_mask, EXIT_TP, reason_local)
            if trig_dte:
                reason_local[:] = EXIT_DTE

            triggered = reason_local > 0
            if triggered.any():
                idx_global = np.where(active)[0][triggered]
                exit_value[idx_global] = strat_val[triggered]
                exit_step[idx_global] = step
                exit_reason[idx_global] = reason_local[triggered]
                active[idx_global] = False

        # remaining sims: hold to expiration -> intrinsic value (no spread offset)
        if active.any():
            ST = paths[active, -1]
            K_grid = K[None, :]
            isc_grid = np.broadcast_to(is_call[None, :], (ST.size, L))
            intrinsic = np.where(
                isc_grid,
                np.maximum(ST[:, None] - K_grid, 0.0),
                np.maximum(K_grid - ST[:, None], 0.0),
            )
            strat_val_terminal = (intrinsic * signs[None, :]).sum(axis=1) \
                * CONTRACT_MULTIPLIER
            exit_value[active] = strat_val_terminal

        total_pnl = entry_value - exit_value
        # NOTE: closing-side transaction costs are NOT charged here, to keep symmetry
        # with `_terminal_pnl` (which only accounts for opening costs via `entry_value`).
        # See monte_carlo_todo.md §1 "Closing-Cost-Asymmetrie".

        stats = {
            "pct_tp":      float(np.mean(exit_reason == EXIT_TP)),
            "pct_sl":      float(np.mean(exit_reason == EXIT_SL)),
            "pct_dte":     float(np.mean(exit_reason == EXIT_DTE)),
            "pct_planned": float(np.mean(exit_reason == EXIT_PLANNED)),
            "pct_expiry":  float(np.mean(exit_reason == EXIT_EXPIRY)),
            "avg_days_in_trade": float(np.mean(exit_step)),
        }
        return total_pnl, entry_value, spread_offset, stats

    # ---------- public: expected value, greeks, analyze ------------------- #
    @log_function
    def calculate_expected_value(
        self, legs: Sequence[OptionLeg],
        management: Optional[ManagementConfig] = None,
    ) -> float:
        if management is not None and management.is_active:
            pnl, _, _, _ = self._managed_pnl(legs, management)
        else:
            pnl, _, _ = self._terminal_pnl(legs)
        disc = np.exp(-self.risk_free_rate * self.time_to_expiration)
        return float(np.mean(pnl) * disc)

    def calculate_expected_value_batch(
        self, strategies: List[Union[Sequence[OptionLeg], List[Dict[str, Any]]]],
        management: Optional[ManagementConfig] = None,
    ) -> List[float]:
        """Calculates expected value for multiple strategies efficiently."""
        results = []
        for s in strategies:
            if isinstance(s[0], dict):
                # Backwards compatibility for list of dicts
                legs = self._legacy_options_to_legs(s) # type: ignore
                results.append(self.calculate_expected_value(legs, management))
            else:
                results.append(self.calculate_expected_value(s, management)) # type: ignore
        return results

    @log_function
    def calculate_greeks(
        self, legs: Sequence[OptionLeg], bump_pct: float = 0.01,
    ) -> Dict[str, float]:
        """Finite-difference greeks. CRN via shared seed across sub-simulators."""
        S0 = self.current_price
        sigma0 = self.volatility
        h = S0 * bump_pct

        def _ev(price: float, vol: float) -> float:
            sub = MonteCarloSimulator(
                current_price=price, volatility=vol, dte=self.dte,
                risk_free_rate=self.risk_free_rate,
                dividend_yield=self.dividend_yield,
                num_simulations=self.num_simulations,
                random_seed=self.random_seed,
                transaction_cost_per_contract=self.transaction_cost_per_contract,
                iv_correction="none",
            )
            return sub.calculate_expected_value(legs)

        ev_up = _ev(S0 + h, sigma0)
        ev_dn = _ev(S0 - h, sigma0)
        ev_mid = _ev(S0, sigma0)
        ev_v = _ev(S0, sigma0 + 0.01)

        delta = (ev_up - ev_dn) / (2 * h)
        gamma = (ev_up - 2 * ev_mid + ev_dn) / (h ** 2)
        vega = (ev_v - ev_mid) / 0.01
        return {"delta": float(delta), "gamma": float(gamma),
                "vega": float(vega)}

    @log_function
    def analyze_strategy(
        self, legs: Sequence[OptionLeg],
        management: Optional[ManagementConfig] = None,
        with_greeks: bool = True,
    ) -> StrategyAnalysis:
        if management is not None and management.is_active:
            pnl, entry_value, spread_offset, mgmt_stats = self._managed_pnl(
                legs, management
            )
        else:
            pnl, entry_value, spread_offset = self._terminal_pnl(legs)
            mgmt_stats = None

        disc = np.exp(-self.risk_free_rate * self.time_to_expiration)
        ev = float(np.mean(pnl) * disc)
        ev_undisc = float(np.mean(pnl))

        win = float(np.mean(pnl > 0))
        loss = float(np.mean(pnl < 0))
        max_profit = float(np.max(pnl))
        max_loss = float(np.min(pnl))
        pcts = {p: float(np.percentile(pnl, p)) for p in (5, 25, 50, 75, 95)}

        breakevens = self._find_breakevens(legs)
        greeks = self.calculate_greeks(legs) if with_greeks else {
            "delta": 0.0, "gamma": 0.0, "vega": 0.0
        }

        return StrategyAnalysis(
            expected_value=ev,
            expected_value_undiscounted=ev_undisc,
            entry_value=entry_value,
            spread_offset=spread_offset,
            win_probability=win,
            loss_probability=loss,
            max_profit=max_profit,
            max_loss=max_loss,
            pnl_percentiles=pcts,
            breakevens=breakevens,
            greeks=greeks,
            management_stats=mgmt_stats,
            extras={"pnl": pnl},
        )

    # ---------- breakevens ------------------------------------------------ #
    def _find_breakevens(self, legs: Sequence[OptionLeg]) -> List[float]:
        """Analytic breakevens from the terminal payoff curve over a stock-price grid."""
        arr = self._legs_to_arrays(legs)
        S_grid = np.linspace(self.current_price * 0.3,
                             self.current_price * 1.7, 1401)
        K = arr["strikes"][None, :]
        is_call = arr["is_call"][None, :]
        is_long = arr["is_long"][None, :]
        intrinsic = np.where(
            is_call,
            np.maximum(S_grid[:, None] - K, 0.0),
            np.maximum(K - S_grid[:, None], 0.0),
        )
        long_pnl = (intrinsic - arr["premiums"][None, :]) * CONTRACT_MULTIPLIER
        short_pnl = (arr["premiums"][None, :] - intrinsic) * CONTRACT_MULTIPLIER
        leg_pnl = np.where(is_long, long_pnl, short_pnl)
        costs = self.transaction_cost_per_contract * len(legs)
        pnl = leg_pnl.sum(axis=1) - costs

        s = np.sign(pnl)
        idx = np.where(np.diff(s) != 0)[0]
        be: List[float] = []
        for i in idx:
            x0, x1 = S_grid[i], S_grid[i + 1]
            y0, y1 = pnl[i], pnl[i + 1]
            if y1 == y0:
                be.append(float((x0 + x1) / 2))
            else:
                be.append(float(x0 - y0 * (x1 - x0) / (y1 - y0)))

        be.sort()
        clustered: List[float] = []
        tol = self.current_price * 0.001
        for x in be:
            if not clustered or abs(x - clustered[-1]) > tol:
                clustered.append(x)
        return clustered



# --------------------------------------------------------------------------- #
#  Backwards compatibility                                                    #
# --------------------------------------------------------------------------- #
class UniversalOptionsMonteCarloSimulator(MonteCarloSimulator):
    """Backwards compatibility alias for MonteCarloSimulator."""

    def calculate_expected_value(self, options: List[Dict[str, Any]], **kwargs) -> float:
        """Legacy API for calculate_expected_value."""
        legs = self._legacy_options_to_legs(options)
        return super().calculate_expected_value(legs)

    def calculate_greeks(self, options: List[Dict[str, Any]], **kwargs) -> Dict[str, float]:
        """Legacy API for calculate_greeks."""
        legs = self._legacy_options_to_legs(options)
        return super().calculate_greeks(legs)

    def _legacy_options_to_legs(self, options: List[Dict[str, Any]]) -> List[OptionLeg]:
        legs = []
        for opt in options:
            is_call = bool(opt['is_call'])
            delta = float(opt.get('delta', 0.0))
            # Fix sign if delta comes in positive from DB
            if not is_call and delta > 0:
                delta = -delta
            
            legs.append(OptionLeg(
                strike=float(opt['strike']),
                premium=float(opt['premium']),
                is_call=is_call,
                is_long=bool(opt['is_long']),
                delta=delta,
                gamma=float(opt.get('gamma', 0.0)),
                vega=float(opt.get('vega', 0.0)),
                theta=float(opt.get('theta', 0.0)),
                iv=float(opt.get('iv', self.volatility))
            ))
        return legs


# --------------------------------------------------------------------------- #
#  Manual debug / demo                                                        #
# --------------------------------------------------------------------------- #
def _print_analysis(name: str, result: "StrategyAnalysis") -> None:
    """Pretty-print a StrategyAnalysis to the console."""
    print("\n" + "=" * 78)
    print(f"  {name}")
    print("=" * 78)
    print(f"  Entry value (USD, signed)      : {result.entry_value:+.2f}")
    print(f"  Spread offset (USD)            : {result.spread_offset:+.2f}")
    print(f"  Expected value (discounted)    : {result.expected_value:+.2f}")
    print(f"  Expected value (undiscounted)  : {result.expected_value_undiscounted:+.2f}")
    print(f"  Win  probability               : {result.win_probability:.2%}")
    print(f"  Loss probability               : {result.loss_probability:.2%}")
    print(f"  Max profit / Max loss (USD)    : {result.max_profit:+.2f} / {result.max_loss:+.2f}")
    print("  PnL percentiles (USD):")
    for p, v in result.pnl_percentiles.items():
        print(f"      P{p:>2}  : {v:+.2f}")
    be_fmt = ", ".join(f"{b:.2f}" for b in result.breakevens) or "–"
    print(f"  Breakevens                     : {be_fmt}")
    g = result.greeks
    print(f"  Greeks  delta/gamma/vega       : "
          f"{g['delta']:+.4f} / {g['gamma']:+.6f} / {g['vega']:+.4f}")
    if result.management_stats is not None:
        s = result.management_stats
        print("  Management exit distribution:")
        print(f"      TP        : {s['pct_tp']:.2%}")
        print(f"      SL        : {s['pct_sl']:.2%}")
        print(f"      DTE close : {s['pct_dte']:.2%}")
        print(f"      Planned   : {s['pct_planned']:.2%}")
        print(f"      Expiry    : {s['pct_expiry']:.2%}")
        print(f"      Avg days in trade : {s['avg_days_in_trade']:.1f}")
    print("=" * 78)


def _metrics(result: "StrategyAnalysis", hold_dte: int) -> Dict[str, float]:
    """Risk- and time-normalised metrics for a single StrategyAnalysis."""
    pnl = result.extras["pnl"]
    ev = float(np.mean(pnl))
    std = float(np.std(pnl, ddof=1))
    p5 = float(np.percentile(pnl, 5))
    cvar5 = float(np.mean(pnl[pnl <= p5])) if np.any(pnl <= p5) else p5

    if result.management_stats is not None:
        avg_days = max(result.management_stats["avg_days_in_trade"], 1.0)
    else:
        avg_days = float(hold_dte)

    return {
        "EV":            ev,
        "EV/day":        ev / avg_days,
        "EV_annualized": ev * (365.0 / avg_days),
        "Std":           std,
        "Sharpe_like":   ev / std if std > 0 else float("nan"),
        "P5":            p5,
        "CVaR_5":        cvar5,
        "EV/|CVaR5|":    ev / abs(cvar5) if cvar5 != 0 else float("nan"),
        "EV/|MaxLoss|":  ev / abs(result.max_loss) if result.max_loss != 0 else float("nan"),
        "WinProb":       result.win_probability,
        "AvgDays":       avg_days,
        "MaxProfit":     result.max_profit,
        "MaxLoss":       result.max_loss,
    }


def compare_variants(managed: "StrategyAnalysis",
                     hold: "StrategyAnalysis",
                     hold_dte: int) -> None:
    """Side-by-side comparison: managed (A) vs hold-to-expiration (B)."""
    m = _metrics(managed, hold_dte)
    h = _metrics(hold, hold_dte)

    rows = [
        ("EV (USD)",                "EV",            "{:+.2f}"),
        ("EV / Tag (USD)",          "EV/day",        "{:+.3f}"),
        ("EV annualisiert (USD)",   "EV_annualized", "{:+.2f}"),
        ("Std(PnL) (USD)",          "Std",           "{:.2f}"),
        ("Sharpe-like  EV/Std",     "Sharpe_like",   "{:+.4f}"),
        ("P5  (USD)",               "P5",            "{:+.2f}"),
        ("CVaR 5%  (USD)",          "CVaR_5",        "{:+.2f}"),
        ("EV / |CVaR5|",            "EV/|CVaR5|",    "{:+.4f}"),
        ("EV / |MaxLoss|",          "EV/|MaxLoss|",  "{:+.4f}"),
        ("Win-Prob",                "WinProb",       "{:.2%}"),
        ("Avg Tage im Trade",       "AvgDays",       "{:.1f}"),
        ("Max Profit (USD)",        "MaxProfit",     "{:+.2f}"),
        ("Max Loss (USD)",          "MaxLoss",       "{:+.2f}"),
    ]

    print("\n" + "=" * 82)
    print("  Vergleich  managed (A)   vs.   hold-to-expiration (B)")
    print("=" * 82)
    print(f"  {'Metrik':<28} {'Managed (A)':>18} {'Hold (B)':>18}   Gewinner")
    print("  " + "-" * 78)
    for label, key, fmt in rows:
        va, vb = m[key], h[key]
        if key == "Std":
            winner = "A" if va < vb else ("B" if vb < va else "=")
        elif key in ("MaxLoss", "P5", "CVaR_5"):
            winner = "A" if va > vb else ("B" if vb > va else "=")
        else:
            winner = "A" if va > vb else ("B" if vb > va else "=")
        print(f"  {label:<28} {fmt.format(va):>18} {fmt.format(vb):>18}   {winner}")
    print("=" * 82)


def bootstrap_ci_mean(pnl: np.ndarray,
                      n_boot: int = 2000,
                      alpha: float = 0.05,
                      rng: Optional[np.random.Generator] = None
                      ) -> Tuple[float, float]:
    """Non-parametric bootstrap CI for the mean of `pnl`."""
    rng = rng if rng is not None else np.random.default_rng(0)
    n = len(pnl)
    means = rng.choice(pnl, size=(n_boot, n), replace=True).mean(axis=1)
    lo = float(np.quantile(means, alpha / 2))
    hi = float(np.quantile(means, 1 - alpha / 2))
    return lo, hi


def annualized_ev_with_redeploy(
    simulator: "MonteCarloSimulator",
    legs: Sequence[OptionLeg],
    management: Optional[ManagementConfig],
    days_per_year: int = 365,
) -> Tuple[float, float, "StrategyAnalysis"]:
    """
    Approximate annualised EV under i.i.d. re-deployment after each exit.
    Returns (annual_ev, trades_per_year, analysis).
    """
    res = simulator.analyze_strategy(legs, management=management)
    if management is not None and management.is_active and res.management_stats is not None:
        avg_days = max(res.management_stats["avg_days_in_trade"], 1.0)
    else:
        avg_days = float(simulator.dte)
    trades_per_year = days_per_year / avg_days
    return res.expected_value * trades_per_year, trades_per_year, res


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # ----- 1. Setup & Strategie-Definition ----- #
    # Beispiel: Iron Condor auf SPY (ca. 45 DTE)
    underlying_price = 395.09
    iv = 0.43
    dte = 44

    # Wir definieren die Legs mit Greeks und Leg-IV für realistisches Pricing (Skew/Smile)
    # Greeks und IVs sind hier beispielhaft gewählt
    # Hinweis: Wir nutzen Credit-Preise (negativ für Short, positiv für Long beim Kauf),
    # aber im Simulator werden Premiums meist als positive Werte für Einnahmen erwartet.
    iron_condor_legs = [
        # Short Put Spread (Wachstum durch Theta, Risiko bei Drop)
        OptionLeg(strike=335.0, premium=4.65, is_call=False, is_long=True,  iv=0.43, delta=0.13, gamma=0.01, vega=0.3, theta=0.05),
        OptionLeg(strike=340.0, premium=5.51, is_call=False, is_long=False, iv=0.43, delta=0.15, gamma=0.012, vega=0.3, theta=0.06),
        # Short Call Spread (Wachstum durch Theta, Risiko bei Rallye)
        OptionLeg(strike=465.0, premium=4.85, is_call=True,  is_long=False, iv=0.43, delta=0.15, gamma=0.011, vega=0.3, theta=0.055),
        OptionLeg(strike=470.0, premium=4.2, is_call=True,  is_long=True,  iv=0.43, delta=0.14, gamma=0.009, vega=0.3, theta=0.045),
    ]

    # Wir berechnen das Net-Premium für die Anzeige
    # net_premium = (1.20 - 0.80) + (1.10 - 0.70) = 0.40 + 0.40 = 0.80
    # Entry Cashflow im Simulator: -0.80 + 1.20 + 1.10 - 0.70 = 0.80 (Credit)

    # Tastytrade Management Konfiguration
    mgmt = ManagementConfig(tp_pct=50.0, sl_pct=200.0, dte_close=21)

    # ----- 2. Szenario A: Baseline (GBM / Hold-to-Expiration) ----- #
    # In einem GBM Modell mit konstanter Vola ist Management oft statistisch "teurer",
    # da kein Vola-Crush stattfindet.
    print("\n" + "="*82)
    print(" SZENARIO 1: HOLD-TO-EXPIRATION (PASSIV) - GBM Modell")
    print("="*82)
    
    sim_gbm = MonteCarloSimulator(
        current_price=underlying_price,
        volatility=iv,
        dte=dte,
        num_simulations=20000,
        iv_correction='auto'
    )
    
    analysis_hold = sim_gbm.analyze_strategy(iron_condor_legs, management=None)
    _print_analysis("Iron Condor - Hold-to-Expiration (GBM)", analysis_hold)

    # ----- 3. Szenario B: Tastytrade-Style (Aktiv) - IV Shock / Vola-Crush ----- #
    # Hier simulieren wir den "Edge": IV ist beim Einstieg hoch und fällt (Mean-Reversion).
    print("\n" + "="*82)
    print(" SZENARIO 2: TASTYTRADE-STYLE (AKTIV) - IV-SHOCK / VOLA-CRUSH")
    print("="*82)
    
    from src.price_models import IVShockModel
    
    # Simulation eines hohen IV-Umfelds (IVR > 50)
    # IV0 (Einstieg) = 20%, Long-Run Mean = 12% (Vola-Crush von 8% geplant)
    iv_shock_model = IVShockModel(
        s0=underlying_price,
        iv0=iv,
        lr_iv=0.12, 
        half_life_days=10.0 # Vola normalisiert sich schneller
    )
    
    sim_tasty = MonteCarloSimulator(
        current_price=underlying_price,
        volatility=iv,
        dte=dte,
        num_simulations=20000,
        price_model=iv_shock_model
    )
    
    analysis_tasty = sim_tasty.analyze_strategy(iron_condor_legs, management=mgmt)
    _print_analysis("Iron Condor - Tastytrade Managed (IV-Shock)", analysis_tasty)

    # ----- 4. Direkter Vergleich ----- #
    print("\n" + "="*82)
    print(" DIREKTER VERGLEICH: HOLD (GBM) VS. TASTYTRADE (IV-SHOCK)")
    print("="*82)
    compare_variants(analysis_tasty, analysis_hold, hold_dte=dte)

    # Bootstrap & Annualisierung
    ci_tasty = bootstrap_ci_mean(analysis_tasty.extras["pnl"])
    ann_tasty, tpy_tasty, _ = annualized_ev_with_redeploy(sim_tasty, iron_condor_legs, mgmt)
    
    print(f"\n  Tastytrade (Managed) 95%-CI: [{ci_tasty[0]:+.2f}, {ci_tasty[1]:+.2f}]")
    print(f"  Erwarteter Jahresertrag (Re-Deployment): {ann_tasty:+.2f} USD ({tpy_tasty:.1f} Trades/Jahr)")
    print("="*82 + "\n")
