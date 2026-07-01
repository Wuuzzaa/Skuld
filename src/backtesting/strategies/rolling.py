"""
Reusable rolling sub-strategies (backtest.md Kap. 6).

The RollingManager is attached to a Strategy via `strategy.rolling_manager`.
The engine calls `check_rolling(portfolio, snapshot)` in each day's
maintenance phase, which dispatches to the concrete `RollStrategy`
based on the position's `tags["roll_strategy"]` key.

The Eric-Ludwig default implements the 4-phase defensive model:
  Phase 1 — vertical (adjust strike down for credit/even)
  Phase 2 — horizontal (roll out in time)
  Phase 3 — vertical again (further strike adjustment)
  Phase 4 — position size (roll to more contracts at lower strike)

Trigger constants are copied from Kap. 6.2 defaults; every one is a
`[PLATZHALTER]` in the spec so we materialize them here as tunable
class attributes and note them for the user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from src.backtesting.engine.actions import AdjustPosition, LegSpec

if TYPE_CHECKING:
    from src.backtesting.data.snapshot import MarketSnapshot
    from src.backtesting.engine.portfolio import OptionLeg, Portfolio, Position

logger = logging.getLogger(__name__)


class RollStrategy:
    """Base class for rolling sub-strategies."""

    def evaluate(
        self, position: "Position", snapshot: "MarketSnapshot"
    ) -> Optional[AdjustPosition]:
        raise NotImplementedError


@dataclass
class EricLudwigStrategy(RollStrategy):
    """
    4-phase defensive rolling model (Kap. 6.2).

    All triggers are configurable. Defaults chosen conservatively.
    """

    # Phase 1 triggers: short-strike delta or ITM threshold
    phase1_delta_trigger: float = 0.60
    phase1_max_rolls: int = 2

    # Phase 2 triggers: DTE fallback and target
    phase2_dte_trigger: int = 14
    phase2_target_dte: int = 45

    # Phase 3 trigger: further move against us
    phase3_pnl_trigger_pct: float = -0.50

    # Phase 4 trigger: exhausted phases 1-3 and still trouble
    phase4_max_contracts: int = 4

    def evaluate(
        self, position: "Position", snapshot: "MarketSnapshot"
    ) -> Optional[AdjustPosition]:
        # Only defensive rolls for short-option positions (single- or multi-leg)
        from src.backtesting.engine.portfolio import OptionLeg

        short_legs = [l for l in position.legs
                      if isinstance(l, OptionLeg) and l.is_short]
        if not short_legs:
            return None

        # Aggregate helpers used across phases
        pnl_pct = position.unrealized_pnl_pct()
        phase = int(position.tags.get("roll_phase", "0"))

        # PHASE 1: delta breach -> strike down for credit/even
        if phase < 1 and self._phase1_trigger(short_legs):
            action = self._roll_strike_down(position, snapshot, short_legs)
            if action:
                position.tags["roll_phase"] = "1"
                return action

        # PHASE 2: DTE too low -> horizontal roll further out
        if phase < 2 and any(l.days_to_expiration <= self.phase2_dte_trigger
                             for l in short_legs):
            action = self._roll_horizontal(position, snapshot, short_legs)
            if action:
                position.tags["roll_phase"] = "2"
                return action

        # PHASE 3: still losing badly -> strike down again
        if phase < 3 and pnl_pct is not None and pnl_pct <= self.phase3_pnl_trigger_pct:
            action = self._roll_strike_down(position, snapshot, short_legs, aggressive=True)
            if action:
                position.tags["roll_phase"] = "3"
                return action

        # PHASE 4: last resort -> double contracts, halve strike distance
        if phase == 3:
            action = self._roll_size_up(position, snapshot, short_legs)
            if action:
                position.tags["roll_phase"] = "4"
                return action

        return None

    # ── Triggers ─────────────────────────────────────────────────────────

    def _phase1_trigger(self, short_legs) -> bool:
        for leg in short_legs:
            if leg.delta is None:
                continue
            if abs(leg.delta) >= self.phase1_delta_trigger:
                return True
        return False

    # ── Rolls ────────────────────────────────────────────────────────────

    def _roll_strike_down(
        self,
        position: "Position",
        snapshot: "MarketSnapshot",
        short_legs,
        aggressive: bool = False,
    ) -> Optional[AdjustPosition]:
        """Close the offending short leg and open a lower-strike replacement."""
        # Pick the leg with the highest |delta| as the one to defend
        target = max(short_legs, key=lambda l: abs(l.delta) if l.delta else 0)
        chain = snapshot.get_chain(target.symbol)
        if chain is None:
            return None
        step = 0.30 if aggressive else 0.20
        new_delta_target = max(0.10, abs(target.delta or step) - step)
        # For puts, delta is negative; for calls, positive. We stay side-consistent
        # because `find(delta_target)` compares on absolute value.
        return AdjustPosition(
            position_id=position.id,
            close_leg_ids=[target.id],
            open_legs=[
                LegSpec(
                    kind="option",
                    symbol=target.symbol,
                    contract_type=target.contract_type,
                    quantity=target.quantity,  # same sign, same # of contracts
                    delta_target=new_delta_target,
                    dte_range=(target.days_to_expiration - 5,
                               target.days_to_expiration + 5),
                )
            ],
            reason="roll_phase1" if not aggressive else "roll_phase3",
        )

    def _roll_horizontal(
        self, position: "Position", snapshot: "MarketSnapshot", short_legs
    ) -> Optional[AdjustPosition]:
        target = min(short_legs, key=lambda l: l.days_to_expiration)
        return AdjustPosition(
            position_id=position.id,
            close_leg_ids=[target.id],
            open_legs=[
                LegSpec(
                    kind="option",
                    symbol=target.symbol,
                    contract_type=target.contract_type,
                    quantity=target.quantity,
                    strike_target=target.strike,
                    dte_range=(self.phase2_target_dte - 7, self.phase2_target_dte + 7),
                )
            ],
            reason="roll_phase2",
        )

    def _roll_size_up(
        self, position: "Position", snapshot: "MarketSnapshot", short_legs
    ) -> Optional[AdjustPosition]:
        target = max(short_legs, key=lambda l: abs(l.delta) if l.delta else 0)
        current_qty = abs(target.quantity)
        new_qty = min(current_qty * 2, self.phase4_max_contracts)
        if new_qty <= current_qty:
            return None
        signed_qty = -new_qty if target.quantity < 0 else new_qty
        return AdjustPosition(
            position_id=position.id,
            close_leg_ids=[target.id],
            open_legs=[
                LegSpec(
                    kind="option",
                    symbol=target.symbol,
                    contract_type=target.contract_type,
                    quantity=signed_qty,
                    delta_target=max(0.10, (abs(target.delta or 0.30) - 0.15)),
                    dte_range=(target.days_to_expiration - 5,
                               target.days_to_expiration + 10),
                )
            ],
            reason="roll_phase4",
        )


@dataclass
class RollingManager:
    """Dispatches per-position rolling logic based on position tags."""

    strategies: dict[str, RollStrategy] = field(default_factory=dict)

    def register(self, key: str, strategy: RollStrategy) -> None:
        self.strategies[key] = strategy

    def check_rolling(
        self, portfolio: "Portfolio", snapshot: "MarketSnapshot"
    ) -> None:
        # Import here to avoid a runtime circular import
        from src.backtesting.execution.executor import Executor

        for position in list(portfolio.open_positions):
            key = position.tags.get("roll_strategy")
            if key is None or key not in self.strategies:
                continue
            action = self.strategies[key].evaluate(position, snapshot)
            if action is None:
                continue
            # Execute the roll inline via a fresh executor using default config.
            # In production we'd receive the run_config, but a default is fine
            # for defensive rolls whose slippage is dominated by market impact.
            from src.backtesting.engine.engine import RunConfig
            Executor(RunConfig()).execute(action, portfolio, snapshot)
