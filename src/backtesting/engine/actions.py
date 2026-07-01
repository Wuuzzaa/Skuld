"""
Action primitives returned by Strategy.on_day.

Every action is a dataclass — the engine dispatches on type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional
from uuid import UUID


@dataclass
class LegSpec:
    """
    Declarative description of one leg of an order.

    Either `option_osi` (specific contract) or the (symbol, contract_type,
    delta_target, dte_range, strike_target) tuple to let the executor pick.
    """

    kind: Literal["stock", "option"]
    symbol: str
    quantity: int  # signed: +long / -short. For options: contracts.
    option_osi: Optional[str] = None
    contract_type: Optional[str] = None  # "call" / "put" (option only)
    delta_target: Optional[float] = None
    dte_range: Optional[tuple[int, int]] = None
    strike_target: Optional[float] = None
    limit_price: Optional[float] = None  # None => market/MOC


@dataclass
class Action:
    """Marker base class."""


@dataclass
class OpenPosition(Action):
    legs: list[LegSpec]
    tags: dict[str, str] = field(default_factory=dict)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    trailing_stop_pct: Optional[float] = None


@dataclass
class ClosePosition(Action):
    position_id: UUID
    reason: str = "strategy"


@dataclass
class ClosePartial(Action):
    position_id: UUID
    fraction: float  # 0..1 — portion of qty to close
    reason: str = "strategy"


@dataclass
class AdjustPosition(Action):
    """
    Roll / hedge: close some legs and open new ones as a single logical action.
    """

    position_id: UUID
    close_leg_ids: list[UUID]
    open_legs: list[LegSpec]
    reason: str = "roll"


@dataclass
class SetStopLoss(Action):
    position_id: UUID
    level: float  # for stocks: price; for options: premium


@dataclass
class SetTrailingStop(Action):
    position_id: UUID
    trail_pct: float  # 0..1


@dataclass
class SetTakeProfit(Action):
    position_id: UUID
    level: float  # for options: target realized-profit fraction of premium
