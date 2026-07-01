"""
Stop-order primitives, checked by the engine each day.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID, uuid4


@dataclass
class StopOrder:
    """Base class."""

    id: UUID = field(default_factory=uuid4)


@dataclass
class StopLossOrder(StopOrder):
    """Trigger when the underlying (or premium, for pure option positions)
    falls to `level`."""

    level: float = 0.0


@dataclass
class TrailingStopOrder(StopOrder):
    """Trigger when the underlying falls by `trail_pct` from the peak
    reached since the order was placed."""

    trail_pct: float = 0.10
    peak: Optional[float] = None


@dataclass
class TakeProfitOrder(StopOrder):
    """Trigger when unrealized P&L on the position reaches `level`
    (absolute currency amount)."""

    level: float = 0.0
