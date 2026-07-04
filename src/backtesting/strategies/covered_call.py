"""
Covered Call template — long 100 shares + short OTM call.

Entry rule:  On any day where we don't already have a CC on `symbol` and
             we hold 100+ shares, sell a call at `delta_target` in
             `dte_range`.
Exit rule:   Buy back the call at `exit_profit_pct` of premium captured;
             let assignment happen at expiry otherwise.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.backtesting.data.universe import UniverseSpec
from src.backtesting.engine.actions import (
    Action, ClosePosition, LegSpec, OpenPosition,
)
from src.backtesting.engine.portfolio import OptionLeg, StockLeg
from src.backtesting.strategies.base import Strategy, StrategyParams
from src.backtesting.strategies.params import NumericParam, TupleParam

if TYPE_CHECKING:
    from src.backtesting.data.snapshot import MarketSnapshot
    from src.backtesting.engine.portfolio import Portfolio

logger = logging.getLogger(__name__)


class CoveredCallStrategy(Strategy):
    name = "Covered Call"
    description = "Long stock + short OTM call. Buy back at profit target."
    preload_fields = ["day_close", "live_stock_price", "iv_rank", "greeks_delta", "open_interest", "day_volume"]

    params = StrategyParams(
        shares_per_symbol=NumericParam(100, range=(100, 1000), step=100),
        delta_target=NumericParam(0.30, range=(0.10, 0.50), step=0.05),
        dte_range=TupleParam((30, 45), constraints="dte"),
        exit_profit_pct=NumericParam(0.50, range=(0.20, 0.95), step=0.05),
    )

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list[Action]:
        actions: list[Action] = []
        shares_qty = int(self.params.shares_per_symbol)
        delta = float(self.params.delta_target)
        dte_range = tuple(self.params.dte_range)
        exit_pct = float(self.params.exit_profit_pct)

        for symbol in snapshot.universe:
            stock = snapshot.get_stock(symbol)
            if stock is None or stock.live_stock_price <= 0:
                continue

            has_cc = any(
                p.symbol == symbol and p.tags.get("template") == "covered_call"
                for p in portfolio.open_positions
            )
            if has_cc:
                # exit rule: close short-call leg at profit target
                for p in portfolio.positions_by_symbol(symbol):
                    if p.tags.get("template") != "covered_call":
                        continue
                    pnl_pct = p.unrealized_pnl_pct()
                    if pnl_pct is not None and pnl_pct >= exit_pct:
                        actions.append(ClosePosition(
                            position_id=p.id, reason=f"target_{exit_pct:.0%}",
                        ))
                continue

            option = snapshot.find_option(
                symbol, "call", delta_target=delta, dte_range=dte_range,
                min_open_interest=100,
            )
            if option is None:
                continue

            cost = stock.live_stock_price * shares_qty
            if cost > portfolio.buying_power:
                continue

            actions.append(OpenPosition(
                legs=[
                    LegSpec(kind="stock", symbol=symbol, quantity=shares_qty),
                    LegSpec(
                        kind="option", symbol=symbol, contract_type="call",
                        quantity=-1, option_osi=option.option_osi,
                    ),
                ],
                tags={"template": "covered_call"},
                reason="entry",
            ))
        return actions
