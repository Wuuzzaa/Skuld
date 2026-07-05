"""
Strategy base class + StrategyParams container.

Every V1 template subclasses `Strategy` and declares its parameters as a
`StrategyParams`. Extra hooks (`on_position_opened`, `on_symbol_dropped`)
are optional; only `on_day` is mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from src.backtesting.data.universe import UniverseSpec
from src.backtesting.strategies.params import Param

if TYPE_CHECKING:
    from src.backtesting.data.snapshot import MarketSnapshot
    from src.backtesting.engine.actions import Action
    from src.backtesting.engine.portfolio import Portfolio, Position


@dataclass
class StrategyParams:
    """A dict-like container of `Param` values with attribute access."""

    _params: dict[str, Param] = field(default_factory=dict)

    def __init__(self, **kwargs: Param):
        object.__setattr__(self, "_params", dict(kwargs))
        object.__setattr__(self, "_values", {k: v.default for k, v in kwargs.items()})

    def __getattr__(self, name: str) -> Any:
        # Called only when normal lookup fails
        if name in ("_params", "_values"):
            raise AttributeError(name)
        if name in self._params:
            return self._values[name]
        raise AttributeError(name)

    def set(self, name: str, value: Any) -> None:
        if name not in self._params:
            raise KeyError(name)
        self._values[name] = value

    def get(self, name: str) -> Any:
        return self._values[name]

    def all(self) -> dict[str, Any]:
        return dict(self._values)

    def specs(self) -> dict[str, Param]:
        return dict(self._params)

    def copy(self) -> "StrategyParams":
        """Return a deep-ish clone: the Param specs are shared (they're
        declarative and immutable in practice), but the values dict is
        independent so per-instance `set(...)` calls don't bleed into
        sibling instances or the class default."""
        clone = StrategyParams.__new__(StrategyParams)
        object.__setattr__(clone, "_params", dict(self._params))
        object.__setattr__(clone, "_values", dict(self._values))
        return clone


class Strategy:
    """Base class for backtest strategies (Bahn 2 API in the spec)."""

    name: str = "Strategy"
    description: str = ""
    params: StrategyParams = StrategyParams()
    universe_default: Optional[UniverseSpec] = None
    preload_fields: list[str] = []
    rolling_manager = None  # optional attribute — set by subclasses
    _logger: Optional["ResultsCollector"] = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Auto-register concrete subclasses (skip abstract intermediates)
        if getattr(cls, "name", None) and cls.name != "Strategy":
            from src.backtesting.strategies.registry import registry
            registry.register(cls)

    def __init__(self):
        # Give each instance its own params copy so per-run `params.set(...)`
        # never leaks into sibling instances or the class default. Required
        # for parallel/Grid-Search backtests (V2) and safer for the UI even
        # in V1, where a fresh instance is created per run.
        cls_params = type(self).params
        if isinstance(cls_params, StrategyParams):
            self.params = cls_params.copy()

    def on_init(self, config) -> None:
        return

    def log_detail(self, symbol: str, message: str, snapshot: "MarketSnapshot", **kwargs) -> None:
        """
        Log a detail for the current day and symbol.
        The message and extra kwargs will be recorded in the Results' detail_log.

        Quantity convention (mirrors the engine's trade-mirror rows):
          * `quantity_change`   — signed delta applied by an action
                                  (positive = buy/add, negative = sell/close).
          * `quantity_position` — remaining balance of the affected leg AFTER
                                  the action (0 for full close).
        Non-trade rows (e.g. "Holding position") should pass
        `quantity_change=0` and `quantity_position=<current balance>`.
        """
        if self._logger:
            self._logger.record_detail(snapshot.date, symbol, message, **kwargs)

    def compute_daily(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> None:
        return

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list["Action"]:
        raise NotImplementedError

    def on_position_opened(
        self, position: "Position", snapshot: "MarketSnapshot"
    ) -> None:
        return

    def on_position_closed(
        self, position: "Position", snapshot: "MarketSnapshot"
    ) -> None:
        return

    def on_symbol_dropped(
        self, symbol: str, snapshot: "MarketSnapshot"
    ) -> None:
        return
