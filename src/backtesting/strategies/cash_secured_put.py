"""
Cash-Secured Put — sell short OTM put, keep cash reserved for assignment.

Entry rule: sell put at `delta_target` in `dte_range`.
Exit rule:  buy back at `exit_profit_pct` of premium.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.backtesting.engine.actions import (
    Action, ClosePosition, LegSpec, OpenPosition,
)
from src.backtesting.strategies.base import Strategy, StrategyParams
from src.backtesting.strategies.params import NumericParam, TupleParam

if TYPE_CHECKING:
    from src.backtesting.data.snapshot import MarketSnapshot
    from src.backtesting.engine.portfolio import Portfolio

logger = logging.getLogger(__name__)


class CashSecuredPutStrategy(Strategy):
    name = "Cash-Secured Put"
    description = "Short OTM put, cash-secured. Buy back at profit target."
    preload_fields = ["day_close", "iv_rank", "greeks_delta", "open_interest", "day_volume"]

    params = StrategyParams(
        delta_target=NumericParam(-0.30, range=(-0.50, -0.10), step=0.05),
        dte_range=TupleParam((30, 45), constraints="dte"),
        exit_profit_pct=NumericParam(0.50, range=(0.20, 0.95), step=0.05),
        max_positions_per_symbol=NumericParam(1, range=(1, 10), step=1),
    )

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list[Action]:
        actions: list[Action] = []
        delta = float(self.params.delta_target)
        dte_range = tuple(self.params.dte_range)
        exit_pct = float(self.params.exit_profit_pct)
        max_per_symbol = int(self.params.max_positions_per_symbol)

        # Exits first
        for p in list(portfolio.open_positions):
            if p.tags.get("template") != "cash_secured_put":
                continue
            pnl_pct = p.unrealized_pnl_pct()
            if pnl_pct is not None and pnl_pct >= exit_pct:
                actions.append(ClosePosition(
                    position_id=p.id, reason=f"target_{exit_pct:.0%}",
                ))

        # Entries
        for symbol in snapshot.universe:
            stock = snapshot.get_stock(symbol)
            if stock is None or stock.day_close <= 0:
                continue
            existing = [
                p for p in portfolio.positions_by_symbol(symbol)
                if p.tags.get("template") == "cash_secured_put"
            ]
            if len(existing) >= max_per_symbol:
                continue

            option = snapshot.find_option(
                symbol, "put", delta_target=delta, dte_range=dte_range,
                min_open_interest=100,
            )
            if option is None:
                continue

            # Cash reserve = strike * 100 (per contract)
            reserve = option.strike * option.shares_per_contract
            if reserve > portfolio.buying_power:
                continue

            actions.append(OpenPosition(
                legs=[
                    LegSpec(
                        kind="option", symbol=symbol, contract_type="put",
                        quantity=-1, option_osi=option.option_osi,
                    ),
                ],
                tags={"template": "cash_secured_put"},
            ))
        return actions
