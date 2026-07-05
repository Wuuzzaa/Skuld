"""
Iron Condor — short call-spread + short put-spread, symmetric width.
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


class IronCondorStrategy(Strategy):
    name = "Iron Condor"
    description = "Short call-spread + short put-spread, symmetric width."
    preload_fields = ["day_close", "live_stock_price", "iv_rank", "greeks_delta", "open_interest", "day_volume"]

    params = StrategyParams(
        short_delta=NumericParam(0.16, range=(0.05, 0.35), step=0.01),
        wing_width=NumericParam(5.0, range=(1.0, 25.0), step=0.5, unit="$"),
        dte_range=TupleParam((30, 45), constraints="dte"),
        exit_profit_pct=NumericParam(0.50, range=(0.20, 0.95), step=0.05),
    )

    def on_day(
        self, snapshot: "MarketSnapshot", portfolio: "Portfolio"
    ) -> list[Action]:
        actions: list[Action] = []
        short_delta: float = float(self.params.short_delta)
        wing_width: float = float(self.params.wing_width)
        dte_range = tuple(self.params.dte_range)
        exit_pct = float(self.params.exit_profit_pct)

        # Exits
        for p in list(portfolio.open_positions):
            if p.tags.get("template") != "iron_condor":
                continue
            pnl_pct = p.unrealized_pnl_pct()
            if pnl_pct is not None and pnl_pct >= exit_pct:
                self.log_detail(
                    p.symbol, f"Closing Iron Condor: Target PnL reached ({pnl_pct:.1%})", snapshot,
                    pnl_pct=pnl_pct, exit_reason="profit_target"
                )
                actions.append(ClosePosition(
                    position_id=p.id, reason=f"target_{exit_pct:.0%}",
                ))
            else:
                # Log holding state with required fields
                # For options, we show the number of contracts (usually based on short legs)
                qty = 0
                if p.legs:
                    qty = abs(p.legs[0].quantity)
                
                self.log_detail(
                    p.symbol, "Holding Iron Condor", snapshot,
                    pnl_pct=pnl_pct, target_pnl=exit_pct,
                    quantity=qty, cost=0, proceeds=0, commission=0
                )

        # Entries
        for symbol in snapshot.universe:
            stock = snapshot.get_stock(symbol)
            underlying_price = stock.live_stock_price if stock else None
            iv_rank = stock.iv_rank if stock else None

            has_ic = any(
                p.symbol == symbol and p.tags.get("template") == "iron_condor"
                for p in portfolio.open_positions
            )
            if has_ic:
                continue

            short_call = snapshot.find_option(
                symbol, "call", delta_target=short_delta,
                dte_range=dte_range, min_open_interest=100,
            )
            short_put = snapshot.find_option(
                symbol, "put", delta_target=short_delta,
                dte_range=dte_range, min_open_interest=100,
            )
            
            if short_call is None or short_put is None:
                self.log_detail(
                    symbol, "Entry skipped: No suitable short legs found", snapshot,
                    underlying_price=underlying_price, iv_rank=iv_rank,
                    target_delta=short_delta, dte_range=dte_range
                )
                continue

            long_call = snapshot.find_option(
                symbol, "call",
                strike_target=short_call.strike + wing_width,
                dte_range=(short_call.days_to_expiration,
                           short_call.days_to_expiration),
                min_open_interest=50,
            )
            long_put = snapshot.find_option(
                symbol, "put",
                strike_target=short_put.strike - wing_width,
                dte_range=(short_put.days_to_expiration,
                           short_put.days_to_expiration),
                min_open_interest=50,
            )
            
            if long_call is None or long_put is None:
                self.log_detail(
                    symbol, "Entry skipped: No suitable wings found", snapshot,
                    underlying_price=underlying_price, iv_rank=iv_rank,
                    short_call=short_call.strike, short_put=short_put.strike,
                    wing_width=wing_width
                )
                continue

            self.log_detail(
                symbol, "Entry: Opening Iron Condor signal", snapshot,
                underlying_price=underlying_price, iv_rank=iv_rank,
                short_call_strike=short_call.strike, long_call_strike=long_call.strike,
                short_put_strike=short_put.strike, long_put_strike=long_put.strike,
                dte=short_call.days_to_expiration
            )
            actions.append(OpenPosition(
                legs=[
                    LegSpec(kind="option", symbol=symbol, contract_type="call",
                            quantity=-1, option_osi=short_call.option_osi),
                    LegSpec(kind="option", symbol=symbol, contract_type="call",
                            quantity=1, option_osi=long_call.option_osi),
                    LegSpec(kind="option", symbol=symbol, contract_type="put",
                            quantity=-1, option_osi=short_put.option_osi),
                    LegSpec(kind="option", symbol=symbol, contract_type="put",
                            quantity=1, option_osi=long_put.option_osi),
                ],
                tags={"template": "iron_condor"},
                reason="entry",
            ))
        return actions
