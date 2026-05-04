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
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from config import (
    IV_CORRECTION_MODE,
    NUM_SIMULATIONS,
    RANDOM_SEED,
    RISK_FREE_RATE,
    TRANSACTION_COST_PER_CONTRACT,
)
from src.decorator_log_function import log_function

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

        self.time_to_expiration = self.dte / DAYS_PER_YEAR
        self.volatility, self.iv_correction_factor = self._apply_iv_correction(
            self.raw_volatility, self.dte, iv_correction
        )

        # local RNG -> no global seed pollution
        self._rng_seed = self.random_seed

        # caches: small dicts, separate for terminal-only vs. full paths
        self._terminal_cache: Dict[tuple, np.ndarray] = {}
        self._path_cache: Dict[tuple, np.ndarray] = {}
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
        return (self.current_price, self.volatility, self.dte,
                self.risk_free_rate, self.dividend_yield,
                self.num_simulations, self._rng_seed)

    def simulate_terminal_prices(self) -> np.ndarray:
        """Single-step GBM: only terminal prices ST. O(N)."""
        key = self._cache_key()
        cached = self._terminal_cache.get(key)
        if cached is not None:
            return cached
        if self.dte == 0:
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
        """Full daily GBM paths, shape (num_simulations, dte+1)."""
        key = self._cache_key()
        cached = self._path_cache.get(key)
        if cached is not None:
            return cached
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
        bs0 = self._black_scholes(
            S=np.array([self.current_price]),
            K=arr["strikes"],
            T=np.array([self.time_to_expiration]),
            r=self.risk_free_rate, sigma=self.volatility,
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
        long_pnl = (intrinsic - arr["premiums"][None, :]) * CONTRACT_MULTIPLIER
        short_pnl = (arr["premiums"][None, :] - intrinsic) * CONTRACT_MULTIPLIER
        leg_pnl = np.where(is_long, long_pnl, short_pnl)
        costs = self.transaction_cost_per_contract * len(legs) * 2  # open + (implicit) close at expiry
        # Note: at expiry only opening costs are real; closing is automatic.
        # Keep symmetric with managed PnL by NOT charging closing costs here:
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
        num_steps = paths.shape[1]
        days_remaining = self.dte - np.arange(num_steps)
        t_years = days_remaining / DAYS_PER_YEAR

        entry_value = self._entry_cashflow(arr)
        entry_bs = self._entry_bs_value(arr)
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
                bs = self._black_scholes(
                    S_grid, K_grid, T_grid,
                    self.risk_free_rate, self.volatility, isc_grid,
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
        # Closing-side transaction costs (opening costs already in entry_value)
        total_pnl = total_pnl - self.transaction_cost_per_contract * L

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    underlying_price = 395.09
    iv = 0.43
    dte = 45

    iron_condor_legs = [
        # short put spread (lower wing)
        OptionLeg(strike=335.0,  premium=4.65, is_call=False, is_long=True),   # long   put
        OptionLeg(strike=340.0,  premium=5.51, is_call=False, is_long=False),  # short  put
        # short call spread (upper wing)
        OptionLeg(strike=465.0, premium=4.85, is_call=True,  is_long=False),  # short  call
        OptionLeg(strike=470.0, premium=4.20, is_call=True,  is_long=True),   # long   call
    ]

    simulator = MonteCarloSimulator(
        current_price=underlying_price,
        volatility=iv,
        dte=dte,
        num_simulations=50000,
    )

    # Variant A: managed
    mgmt = ManagementConfig(tp_pct=50.0, sl_pct=200.0, dte_close=21)
    analysis_managed = simulator.analyze_strategy(iron_condor_legs, management=mgmt)
    _print_analysis("Iron Condor A — managed (TP 50 % / SL 200 % / DTE close 21)",
                    analysis_managed)

    # Variant B: hold to expiration (no management)
    analysis_holdto_exp = simulator.analyze_strategy(iron_condor_legs, management=None)
    _print_analysis("Iron Condor B — hold to expiration (no management)",
                    analysis_holdto_exp)
