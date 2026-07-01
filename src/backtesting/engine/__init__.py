"""Engine package: main loop, portfolio, positions, actions, stop-orders."""

from src.backtesting.engine.actions import (
    Action,
    OpenPosition,
    ClosePosition,
    ClosePartial,
    AdjustPosition,
    SetStopLoss,
    SetTrailingStop,
    SetTakeProfit,
    LegSpec,
)
from src.backtesting.engine.portfolio import (
    Portfolio,
    Position,
    StockLeg,
    OptionLeg,
)
from src.backtesting.engine.stop_orders import (
    StopOrder,
    StopLossOrder,
    TrailingStopOrder,
    TakeProfitOrder,
)
from src.backtesting.engine.calendar import trading_days
from src.backtesting.engine.engine import run, RunConfig

__all__ = [
    "Action", "OpenPosition", "ClosePosition", "ClosePartial", "AdjustPosition",
    "SetStopLoss", "SetTrailingStop", "SetTakeProfit", "LegSpec",
    "Portfolio", "Position", "StockLeg", "OptionLeg",
    "StopOrder", "StopLossOrder", "TrailingStopOrder", "TakeProfitOrder",
    "trading_days",
    "run", "RunConfig",
]
