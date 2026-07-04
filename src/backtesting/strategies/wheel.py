"""
Wheel — cycle CSP -> assignment -> CC -> called-away -> CSP.

Uses `tags["stage"]` on positions to track the wheel phase.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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


class WheelStrategy(Strategy):
    name = "Wheel"
    description = "CSP -> Assignment -> Covered Call -> Called Away -> CSP loop."
    preload_fields = ["day_close", "iv_rank", "greeks_delta", "open_interest", "day_volume"]

    params = StrategyParams(
        put_delta_target=NumericParam(-0.30, range=(-0.50, -0.10), step=0.05),
        call_delta_target=NumericParam(0.30, range=(0.10, 0.50), step=0.05),
        dte_range=TupleParam((30, 45), constraints="dte"),
        exit_profit_pct=NumericParam(0.50, range=(0.20, 0.95), step=0.05),
    )

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list[Action]:
        actions: list[Action] = []
        put_delta = float(self.params.put_delta_target)
        call_delta = float(self.params.call_delta_target)
        dte_range = tuple(self.params.dte_range)
        exit_pct = float(self.params.exit_profit_pct)

        # 1) Handle exits (take-profit on any open option leg of the wheel)
        for p in list(portfolio.open_positions):
            if p.tags.get("template") != "wheel":
                continue
            pnl_pct = p.unrealized_pnl_pct()
            if pnl_pct is not None and pnl_pct >= exit_pct:
                actions.append(ClosePosition(
                    position_id=p.id, reason=f"target_{exit_pct:.0%}",
                ))

        # 2) Per symbol: decide next entry based on current wheel state
        for symbol in snapshot.universe:
            wheel_positions = [
                p for p in portfolio.positions_by_symbol(symbol)
                if p.tags.get("template") == "wheel"
            ]
            has_short_put = any(
                any(isinstance(l, OptionLeg) and l.is_put and l.is_short
                    for l in p.legs)
                for p in wheel_positions
            )
            has_stock = any(
                any(isinstance(l, StockLeg) and l.quantity > 0 for l in p.legs)
                for p in wheel_positions
            )
            has_short_call = any(
                any(isinstance(l, OptionLeg) and l.is_call and l.is_short
                    for l in p.legs)
                for p in wheel_positions
            )

            stock = snapshot.get_stock(symbol)
            if stock is None or stock.day_close <= 0:
                continue

            if has_stock and not has_short_call:
                # ASSIGNED: sell a call against the shares
                option = snapshot.find_option(
                    symbol, "call", delta_target=call_delta,
                    dte_range=dte_range, min_open_interest=100,
                )
                if option is not None:
                    for p in wheel_positions:
                        stock_leg = next(
                            (l for l in p.legs if isinstance(l, StockLeg)
                             and l.quantity >= 100),
                            None,
                        )
                        if stock_leg is None:
                            continue
                        actions.append(OpenPosition(
                            legs=[LegSpec(
                                kind="option", symbol=symbol,
                                contract_type="call", quantity=-1,
                                option_osi=option.option_osi,
                            )],
                            tags={"template": "wheel", "stage": "cc"},
                        ))
                        break
                continue

            if not has_short_put and not has_stock:
                # CASH: sell a put to enter the wheel
                option = snapshot.find_option(
                    symbol, "put", delta_target=put_delta,
                    dte_range=dte_range, min_open_interest=100,
                )
                if option is None:
                    continue
                reserve = option.strike * option.shares_per_contract
                if reserve > portfolio.buying_power:
                    continue
                actions.append(OpenPosition(
                    legs=[LegSpec(
                        kind="option", symbol=symbol, contract_type="put",
                        quantity=-1, option_osi=option.option_osi,
                    )],
                    tags={"template": "wheel", "stage": "csp"},
                ))
        return actions
