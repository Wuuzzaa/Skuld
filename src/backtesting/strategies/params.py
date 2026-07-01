"""
Declarative strategy parameters — consumed by the frontend to auto-generate
input forms (see backtest.md Kap. 5.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Param:
    default: Any
    label: Optional[str] = None
    description: Optional[str] = None


@dataclass
class NumericParam(Param):
    range: Optional[tuple[float, float]] = None
    step: Optional[float] = None
    unit: Optional[str] = None


@dataclass
class TupleParam(Param):
    """
    Two-value parameter (typically for ranges: (lo, hi)).

    `constraints`: freeform tag consumed by the UI (e.g. "dte") to render
    an appropriate widget.
    """

    constraints: Optional[str] = None
    range: Optional[tuple[float, float]] = None


@dataclass
class ChoiceParam(Param):
    choices: list[Any] = field(default_factory=list)


@dataclass
class BoolParam(Param):
    pass
