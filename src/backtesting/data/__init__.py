"""Data-layer package: Snapshot, loader, universe, filter whitelist, validator."""

from src.backtesting.data.snapshot import (
    MarketSnapshot,
    StockData,
    OptionChain,
    Option,
)
from src.backtesting.data.universe import (
    UniverseSpec,
    UniverseFilter,
    Universe,
    resolve_universe,
)
from src.backtesting.data.loader import SmartPreloader, estimate_ram_gb
from src.backtesting.data.fields import (
    FILTER_FIELDS,
    FIELD_CATEGORIES,
    field_definition,
)
from src.backtesting.data.validator import (
    validate_universe_and_range,
    ValidationResult,
)

__all__ = [
    "MarketSnapshot",
    "StockData",
    "OptionChain",
    "Option",
    "UniverseSpec",
    "UniverseFilter",
    "Universe",
    "resolve_universe",
    "SmartPreloader",
    "estimate_ram_gb",
    "FILTER_FIELDS",
    "FIELD_CATEGORIES",
    "field_definition",
    "validate_universe_and_range",
    "ValidationResult",
]
