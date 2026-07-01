"""Strategy package: base + params + registry + V1 templates + rolling."""

from src.backtesting.strategies.base import Strategy, StrategyParams
from src.backtesting.strategies.params import (
    NumericParam, TupleParam, ChoiceParam, BoolParam,
)
from src.backtesting.strategies.registry import registry
from src.backtesting.strategies.rolling import (
    RollingManager, RollStrategy, EricLudwigStrategy,
)

# Register V1 templates so the frontend can list them
from src.backtesting.strategies import covered_call as _cc  # noqa: F401
from src.backtesting.strategies import cash_secured_put as _csp  # noqa: F401
from src.backtesting.strategies import wheel as _wheel  # noqa: F401
from src.backtesting.strategies import vertical_spread as _vs  # noqa: F401
from src.backtesting.strategies import iron_condor as _ic  # noqa: F401

__all__ = [
    "Strategy", "StrategyParams",
    "NumericParam", "TupleParam", "ChoiceParam", "BoolParam",
    "registry",
    "RollingManager", "RollStrategy", "EricLudwigStrategy",
]
