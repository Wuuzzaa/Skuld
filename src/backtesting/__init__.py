"""
Skuld Backtesting Framework — V1.

Strategy-neutral EOD-based backtesting subsystem for the Skuld options platform.

See `backtest.md` at the repo root for the full V1 design.

Package layout:
    engine/       Main loop, portfolio, positions, actions, stop-orders, calendar
    data/         Snapshot, smart preloader, universe, filter whitelist, validator
    strategies/   Strategy base + StrategyParams + registry + V1 templates
    execution/    Slippage, commission, margin (Reg-T), expiries, corporate actions
    results/      Collector, metrics, benchmark, file storage, export
"""

from src.backtesting.engine.engine import run
from src.backtesting.engine.portfolio import Portfolio, Position
from src.backtesting.engine.actions import (
    Action,
    OpenPosition,
    ClosePosition,
    ClosePartial,
    AdjustPosition,
    SetStopLoss,
    SetTrailingStop,
    SetTakeProfit,
)
from src.backtesting.data.snapshot import MarketSnapshot, StockData, OptionChain, Option
from src.backtesting.data.universe import UniverseSpec, UniverseFilter, Universe
from src.backtesting.strategies.base import Strategy, StrategyParams
from src.backtesting.strategies.registry import registry

__all__ = [
    "run",
    "Portfolio",
    "Position",
    "Action",
    "OpenPosition",
    "ClosePosition",
    "ClosePartial",
    "AdjustPosition",
    "SetStopLoss",
    "SetTrailingStop",
    "SetTakeProfit",
    "MarketSnapshot",
    "StockData",
    "OptionChain",
    "Option",
    "UniverseSpec",
    "UniverseFilter",
    "Universe",
    "Strategy",
    "StrategyParams",
    "registry",
]
