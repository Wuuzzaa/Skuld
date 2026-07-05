"""
Buy and Hold strategy — Buy on first day, sell on last day.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.backtesting.engine.actions import (
    Action, ClosePosition, LegSpec, OpenPosition,
)
from src.backtesting.strategies.base import Strategy, StrategyParams
from src.backtesting.strategies.params import NumericParam

if TYPE_CHECKING:
    from src.backtesting.data.snapshot import MarketSnapshot
    from src.backtesting.engine.portfolio import Portfolio

logger = logging.getLogger(__name__)


class BuyAndHoldStrategy(Strategy):
    name = "Buy and Hold"
    description = "Buys stocks on the first day and sells them on the last day of the backtest."
    preload_fields = ["live_stock_price"]

    params = StrategyParams(
        shares_per_symbol=NumericParam(100, range=(1, 10000), step=1),
    )

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list[Action]:
        actions: list[Action] = []
        shares_qty = int(self.params.shares_per_symbol)

        # 1. Check if we are at the last day -> Sell everything
        if snapshot.is_last_day:
            for p in portfolio.open_positions:
                if p.tags.get("template") == "buy_and_hold":
                    self.log_detail(
                        p.symbol, "Closing position: End of backtest", snapshot
                    )
                    actions.append(ClosePosition(
                        position_id=p.id, reason="end_of_backtest",
                    ))
            return actions

        # 2. Entry rule: Buy at the beginning (if not already holding)
        for symbol in snapshot.universe:
            stock = snapshot.get_stock(symbol)
            price = stock.live_stock_price if stock else None
            
            has_pos = any(
                p.symbol == symbol and p.tags.get("template") == "buy_and_hold"
                for p in portfolio.open_positions
            )
            
            if not has_pos:
                if stock is None or stock.live_stock_price <= 0:
                    self.log_detail(symbol, "Skipping: No price data available", snapshot)
                    continue
                
                cost = stock.live_stock_price * shares_qty
                if cost > portfolio.buying_power:
                    self.log_detail(
                        symbol, "Insufficient buying power", snapshot,
                        price=price, cost=cost, buying_power=portfolio.buying_power
                    )
                    logger.warning(f"Insufficient buying power to buy {shares_qty} shares of {symbol} at {snapshot.date}")
                    continue

                self.log_detail(symbol, "Entry: Initial buy signal", snapshot)
                actions.append(OpenPosition(
                    legs=[LegSpec(kind="stock", symbol=symbol, quantity=shares_qty)],
                    tags={"template": "buy_and_hold"},
                    reason="initial_buy",
                ))
            else:
                # Log state for existing position
                pos = next(p for p in portfolio.open_positions 
                           if p.symbol == symbol and p.tags.get("template") == "buy_and_hold")
                current_qty = sum(l.quantity for l in pos.legs)
                self.log_detail(
                    symbol, "Holding position", snapshot,
                    price=price, quantity_change=0, quantity_position=current_qty,
                    cost=0, proceeds=0, commission=0,
                )

        return actions
