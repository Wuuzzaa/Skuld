"""
Vertical Spread — Bull-Put / Bear-Call / Bull-Call / Bear-Put.

One class, four variants selected via `variant` param.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.backtesting.engine.actions import (
    Action, ClosePosition, LegSpec, OpenPosition,
)
from src.backtesting.strategies.base import Strategy, StrategyParams
from src.backtesting.strategies.params import ChoiceParam, NumericParam, TupleParam

if TYPE_CHECKING:
    from src.backtesting.data.snapshot import MarketSnapshot
    from src.backtesting.engine.portfolio import Portfolio

logger = logging.getLogger(__name__)


VARIANTS = ["bull_put", "bear_call", "bull_call", "bear_put"]


class VerticalSpreadStrategy(Strategy):
    name = "Vertical Spread"
    description = "Bull-Put / Bear-Call / Bull-Call / Bear-Put spreads."
    preload_fields = ["day_close", "live_stock_price", "iv_rank", "greeks_delta", "open_interest", "day_volume"]

    params = StrategyParams(
        variant=ChoiceParam("bull_put", choices=VARIANTS),
        short_delta=NumericParam(0.30, range=(0.10, 0.50), step=0.05),
        wing_width=NumericParam(5.0, range=(1.0, 25.0), step=0.5, unit="$"),
        dte_range=TupleParam((30, 45), constraints="dte"),
        exit_profit_pct=NumericParam(0.50, range=(0.20, 0.95), step=0.05),
    )

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list[Action]:
        actions: list[Action] = []
        variant: str = self.params.variant
        short_delta: float = float(self.params.short_delta)
        wing_width: float = float(self.params.wing_width)
        dte_range = tuple(self.params.dte_range)
        exit_pct = float(self.params.exit_profit_pct)

        # Exits
        for p in list(portfolio.open_positions):
            if p.tags.get("template") != "vertical_spread":
                continue
            pnl_pct = p.unrealized_pnl_pct()
            if pnl_pct is not None and pnl_pct >= exit_pct:
                actions.append(ClosePosition(
                    position_id=p.id, reason=f"target_{exit_pct:.0%}",
                ))

        # Entries
        for symbol in snapshot.universe:
            has_existing = any(
                p.symbol == symbol
                and p.tags.get("template") == "vertical_spread"
                and p.tags.get("variant") == variant
                for p in portfolio.open_positions
            )
            if has_existing:
                continue

            spec = self._build_spread(
                symbol, snapshot, variant, short_delta, wing_width, dte_range,
            )
            if spec is None:
                continue

            actions.append(OpenPosition(
                legs=spec,
                tags={"template": "vertical_spread", "variant": variant},
                reason=f"entry_{variant}",
            ))
        return actions

    def _build_spread(
        self,
        symbol: str,
        snapshot: "MarketSnapshot",
        variant: str,
        short_delta: float,
        wing_width: float,
        dte_range,
    ):
        contract_type = "put" if variant in ("bull_put", "bear_put") else "call"
        short_side_short = variant in ("bull_put", "bear_call")

        short = snapshot.find_option(
            symbol, contract_type, delta_target=short_delta,
            dte_range=dte_range, min_open_interest=100,
        )
        if short is None:
            return None

        if variant == "bull_put":
            long_strike = short.strike - wing_width
        elif variant == "bear_call":
            long_strike = short.strike + wing_width
        elif variant == "bull_call":
            long_strike = short.strike - wing_width  # short call closer to money
        else:  # bear_put
            long_strike = short.strike + wing_width

        long = snapshot.find_option(
            symbol, contract_type, strike_target=long_strike,
            dte_range=(short.days_to_expiration, short.days_to_expiration),
            min_open_interest=50,
        )
        if long is None:
            return None
        if long.option_osi == short.option_osi:
            return None

        short_qty = -1 if short_side_short else 1
        long_qty = 1 if short_side_short else -1

        return [
            LegSpec(kind="option", symbol=symbol, contract_type=contract_type,
                    quantity=short_qty, option_osi=short.option_osi),
            LegSpec(kind="option", symbol=symbol, contract_type=contract_type,
                    quantity=long_qty, option_osi=long.option_osi),
        ]
