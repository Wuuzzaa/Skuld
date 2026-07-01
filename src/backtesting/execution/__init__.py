"""Execution package: slippage, commission, margin (Reg-T), corp actions."""

from src.backtesting.execution.slippage import SlippageModel, oi_based_slippage
from src.backtesting.execution.commission import CommissionCalculator, CommissionConfig
from src.backtesting.execution.margin import RegTMarginCalculator
from src.backtesting.execution.executor import Executor

__all__ = [
    "SlippageModel", "oi_based_slippage",
    "CommissionCalculator", "CommissionConfig",
    "RegTMarginCalculator",
    "Executor",
]
