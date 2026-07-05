"""
Portfolio + Position + Leg.

Multi-leg structures are ONE Position with multiple legs (Covered Call =
Stock + short Call; Iron Condor = 4 option legs) — analogous to IB. This
enables natural P&L aggregation and tagging.

Multiple parallel positions on the same underlying are allowed
(e.g. Wheel running three covered calls on SPY).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional, Union
from uuid import UUID, uuid4

from src.backtesting.data.snapshot import MarketSnapshot, Option
from src.backtesting.engine.stop_orders import (
    StopLossOrder,
    StopOrder,
    TakeProfitOrder,
    TrailingStopOrder,
)

logger = logging.getLogger(__name__)


# ── Legs ─────────────────────────────────────────────────────────────────

@dataclass
class StockLeg:
    """Long or short position in the underlying."""

    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    quantity: int = 0  # signed: +long / -short
    entry_price: float = 0.0
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.entry_price) * self.quantity


@dataclass
class OptionLeg:
    """Long or short option contract."""

    id: UUID = field(default_factory=uuid4)
    symbol: str = ""
    option_osi: str = ""
    contract_type: str = ""  # "call" or "put"
    strike: float = 0.0
    expiration_date: Optional[date] = None
    quantity: int = 0  # signed: +long / -short. Number of CONTRACTS.
    entry_premium: float = 0.0  # per share
    current_premium: float = 0.0  # per share
    shares_per_contract: int = 100
    days_to_expiration: int = 0
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    implied_volatility: Optional[float] = None

    @property
    def market_value(self) -> float:
        return self.current_premium * self.quantity * self.shares_per_contract

    @property
    def unrealized_pnl(self) -> float:
        # For SHORT options, entry premium is a credit; profit as premium falls.
        return (
            (self.entry_premium - self.current_premium) * -self.quantity
            * self.shares_per_contract
        )

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def is_call(self) -> bool:
        return self.contract_type.lower() == "call"

    @property
    def is_put(self) -> bool:
        return self.contract_type.lower() == "put"


Leg = Union[StockLeg, OptionLeg]


# ── Position ─────────────────────────────────────────────────────────────

@dataclass
class Position:
    id: UUID = field(default_factory=uuid4)
    legs: list[Leg] = field(default_factory=list)
    opened_at: Optional[date] = None
    closed_at: Optional[date] = None
    entry_cashflow: float = 0.0  # cash impact at open (credit +ve, debit -ve)
    realized_pnl: float = 0.0
    stop_orders: list[StopOrder] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    # ── Convenience ──────────────────────────────────────────────────────

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    @property
    def symbol(self) -> str:
        """Primary underlying (first leg's symbol)."""
        return self.legs[0].symbol if self.legs else ""

    @property
    def market_value(self) -> float:
        return sum(leg.market_value for leg in self.legs)

    @property
    def unrealized_pnl(self) -> float:
        return sum(leg.unrealized_pnl for leg in self.legs)

    @property
    def dte(self) -> Optional[int]:
        """Minimum DTE across all option legs. None if no options."""
        dtes = [
            leg.days_to_expiration
            for leg in self.legs
            if isinstance(leg, OptionLeg)
        ]
        return min(dtes) if dtes else None

    @property
    def delta_current(self) -> Optional[float]:
        """Aggregate delta across option legs (signed by quantity).
        Stock legs contribute 1.0 per share."""
        delta = 0.0
        has_any = False
        for leg in self.legs:
            if isinstance(leg, OptionLeg) and leg.delta is not None:
                delta += leg.delta * leg.quantity * leg.shares_per_contract
                has_any = True
            elif isinstance(leg, StockLeg):
                delta += 1.0 * leg.quantity
                has_any = True
        return delta if has_any else None

    def distance_to_strike_pct(self, snapshot: MarketSnapshot) -> Optional[float]:
        """
        Signed % distance from underlying to the nearest short-option strike.
        Positive = underlying above short strike.
        """
        stock = snapshot.get_stock(self.symbol)
        if stock is None:
            return None
        short_strikes = [
            leg.strike
            for leg in self.legs
            if isinstance(leg, OptionLeg) and leg.is_short
        ]
        if not short_strikes:
            return None
        nearest_strike = min(short_strikes, key=lambda s: abs(s - stock.live_stock_price))
        if nearest_strike == 0:
            return None
        return (stock.live_stock_price - nearest_strike) / nearest_strike

    def unrealized_pnl_pct(self) -> Optional[float]:
        """Unrealized P&L relative to entry cash flow."""
        if self.entry_cashflow == 0:
            return None
        return self.unrealized_pnl / abs(self.entry_cashflow)

    @property
    def roll_count(self) -> int:
        return int(self.tags.get("roll_count", "0"))


# ── Portfolio ────────────────────────────────────────────────────────────

@dataclass
class Portfolio:
    cash: float = 0.0
    positions: list[Position] = field(default_factory=list)
    closed_positions: list[Position] = field(default_factory=list)
    margin_used: float = 0.0
    config: dict = field(default_factory=dict)
    # Optional callback fired exactly once per position when it moves to
    # closed. Wired by the engine to ResultsCollector.on_position_closed
    # so `results.position_log` becomes a direct record of what actually
    # happened, not a rebuild-from-trade-log after the fact.
    on_position_closed: Optional[Callable[["Position"], None]] = field(
        default=None, repr=False
    )

    # ── Basic accessors ──────────────────────────────────────────────────

    @property
    def equity(self) -> float:
        return self.cash + sum(p.market_value for p in self.positions)

    @property
    def buying_power(self) -> float:
        return self.cash - self.margin_used

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if not p.is_closed]

    def get_position(self, position_id: UUID) -> Optional[Position]:
        for p in self.positions:
            if p.id == position_id:
                return p
        return None

    def positions_by_symbol(self, symbol: str) -> list[Position]:
        return [p for p in self.open_positions if p.symbol == symbol]

    def positions_by_tag(self, tag_key: str, tag_value: str) -> list[Position]:
        return [
            p for p in self.open_positions
            if p.tags.get(tag_key) == tag_value
        ]

    # ── Daily maintenance ────────────────────────────────────────────────

    def mark_to_market(self, snapshot: MarketSnapshot) -> None:
        """Update `current_price` / `current_premium` on all legs from
        the snapshot."""
        for position in self.open_positions:
            for leg in position.legs:
                if isinstance(leg, StockLeg):
                    stock = snapshot.get_stock(leg.symbol)
                    if stock:
                        leg.current_price = stock.live_stock_price
                elif isinstance(leg, OptionLeg):
                    chain = snapshot.get_chain(leg.symbol)
                    if chain:
                        for opt in chain.all():
                            if opt.option_osi == leg.option_osi:
                                leg.current_premium = opt.day_close
                                leg.days_to_expiration = opt.days_to_expiration
                                leg.delta = opt.delta
                                leg.gamma = opt.gamma
                                leg.theta = opt.theta
                                leg.vega = opt.vega
                                leg.implied_volatility = opt.implied_volatility
                                break

    def apply_dividends(self, snapshot: MarketSnapshot) -> None:
        """
        V1 simplification: if a stock leg is held and today == last_dividend_date,
        credit `last_dividend * shares` to cash.
        """
        for position in self.open_positions:
            for leg in position.legs:
                if not isinstance(leg, StockLeg):
                    continue
                stock = snapshot.get_stock(leg.symbol)
                if stock is None or stock.last_dividend is None:
                    continue
                if stock.last_dividend_date == snapshot.date:
                    div = stock.last_dividend * leg.quantity
                    self.cash += div
                    logger.debug(
                        "Dividend %.2f paid on %s (qty=%d)",
                        div, leg.symbol, leg.quantity,
                    )

    def apply_splits(self, snapshot: MarketSnapshot) -> None:
        """
        V1: no-op. Skuld's DB currently doesn't expose split events explicitly;
        the historized OHLC is already split-adjusted. Kept as a stable hook
        so strategies + tests can rely on the method's presence.
        """
        return

    def apply_expiries(self, snapshot: MarketSnapshot) -> None:
        """Handle option-leg expirations: ITM => assignment, OTM => worthless.

        When the last leg of a position expires (OTM) or gets fully
        assigned into a delivered stock leg that then leaves the position,
        we close the position via `_move_to_closed`. `realized_pnl` is the
        sum of (entry cash flow) + (all assignment cash flows) — computed
        here per-position so the collector's position_log records the
        true P&L, not a reconstructed number.
        """
        for position in self.open_positions:
            expired_any = False
            expiry_cashflow = 0.0
            for leg in list(position.legs):
                if not isinstance(leg, OptionLeg):
                    continue
                if leg.expiration_date is None or leg.expiration_date > snapshot.date:
                    continue

                stock = snapshot.get_stock(leg.symbol)
                stock_price = stock.live_stock_price if stock else leg.strike
                itm = (leg.is_call and stock_price > leg.strike) or (
                    leg.is_put and stock_price < leg.strike
                )
                if itm:
                    expiry_cashflow += self._settle_assignment(
                        position, leg, stock_price
                    )
                else:
                    # OTM: leg simply vanishes; premium was already realized at open
                    position.legs.remove(leg)
                expired_any = True

            if expired_any and not any(
                isinstance(l, (StockLeg, OptionLeg)) for l in position.legs
            ):
                position.closed_at = snapshot.date
                position.realized_pnl = position.entry_cashflow + expiry_cashflow
                position.tags.setdefault("close_reason", "expiry")
                self._move_to_closed(position)

    def _settle_assignment(
        self, position: Position, leg: OptionLeg, stock_price: float
    ) -> float:
        """
        Short ITM call: shares delivered, cash += strike * qty * shares.
        Long ITM call: opposite (rare in defensive strategies).
        Short ITM put: shares assigned, cash -= strike * qty * shares.
        Long ITM put: opposite.

        Returns the cash delta booked to the portfolio so the caller
        (`apply_expiries`) can accumulate it into `position.realized_pnl`.
        """
        cash_delta = -leg.strike * leg.quantity * leg.shares_per_contract
        stock_qty_delta = leg.quantity * leg.shares_per_contract
        if leg.is_call:
            # short call ITM (qty < 0): shares GO OUT, cash IN
            #   quantity=-1 -> stock_qty_delta=-100, cash_delta=+strike*100 ✓
            pass
        else:
            # short put ITM (qty < 0): shares COME IN, cash OUT
            #   quantity=-1 -> stock_qty_delta=-100, cash_delta=+strike*100
            #   ... flip signs: puts trade the opposite direction
            stock_qty_delta = -stock_qty_delta
            cash_delta = -cash_delta

        self.cash += cash_delta

        # Merge with existing stock leg if present; else create one
        existing_stock = next(
            (l for l in position.legs if isinstance(l, StockLeg)
             and l.symbol == leg.symbol),
            None,
        )
        if existing_stock is not None:
            new_qty = existing_stock.quantity + stock_qty_delta
            if new_qty == 0:
                position.legs.remove(existing_stock)
            else:
                # Weighted-average entry price
                total_cost = (
                    existing_stock.entry_price * existing_stock.quantity
                    + leg.strike * stock_qty_delta
                )
                existing_stock.entry_price = total_cost / new_qty
                existing_stock.quantity = new_qty
                existing_stock.current_price = stock_price
        elif stock_qty_delta != 0:
            position.legs.append(
                StockLeg(
                    symbol=leg.symbol,
                    quantity=stock_qty_delta,
                    entry_price=leg.strike,
                    current_price=stock_price,
                )
            )

        position.legs.remove(leg)
        return cash_delta

    def check_dte_close(self, snapshot: MarketSnapshot) -> None:
        """Auto-close option positions whose min-DTE <= threshold."""
        threshold = self.config.get("dte_close_threshold")
        if threshold is None:
            return

        for position in list(self.open_positions):
            dte = position.dte
            if dte is None:
                continue
            if dte <= threshold:
                self.close_position(position, snapshot, reason="dte_close")

    def check_rolling(self, snapshot: MarketSnapshot, strategy) -> None:
        """Delegate to RollingManager if the strategy provides one."""
        rolling_manager = getattr(strategy, "rolling_manager", None)
        if rolling_manager is None:
            return
        rolling_manager.check_rolling(self, snapshot)

    def check_stop_orders(self, snapshot: MarketSnapshot) -> None:
        """Evaluate SL / Trailing / TP for each open position."""
        for position in list(self.open_positions):
            for stop in list(position.stop_orders):
                triggered, reason = self._evaluate_stop(position, stop, snapshot)
                if triggered:
                    self.close_position(position, snapshot, reason=reason)
                    break  # position closed; skip remaining stops on it

    def _evaluate_stop(
        self, position: Position, stop: StopOrder, snapshot: MarketSnapshot
    ) -> tuple[bool, str]:
        stock = snapshot.get_stock(position.symbol)
        if stock is None:
            return False, ""

        if isinstance(stop, StopLossOrder):
            if stock.live_stock_price <= stop.level:
                return True, "stop_loss"
        elif isinstance(stop, TrailingStopOrder):
            if stop.peak is None or stock.live_stock_price > stop.peak:
                stop.peak = stock.live_stock_price
            if stop.peak is not None:
                threshold = stop.peak * (1 - stop.trail_pct)
                if stock.live_stock_price <= threshold:
                    return True, "trailing_stop"
        elif isinstance(stop, TakeProfitOrder):
            if position.unrealized_pnl >= stop.level:
                return True, "take_profit"
        return False, ""

    def enforce_universe(
        self, snapshot: MarketSnapshot, active_universe: list[str]
    ) -> None:
        """Hard-exit STOCK-only positions whose symbol left the universe."""
        active = set(active_universe)
        for position in list(self.open_positions):
            if position.symbol in active:
                continue
            has_options = any(isinstance(l, OptionLeg) for l in position.legs)
            if has_options:
                continue  # options keep running until managed by strategy
            self.close_position(position, snapshot, reason="universe_exit")

    # ── Position lifecycle ───────────────────────────────────────────────

    def close_position(
        self, position: Position, snapshot: MarketSnapshot, reason: str = "strategy"
    ) -> float:
        """
        Close all legs at current market prices. Returns realized cashflow.
        Ignores commission/slippage — those are applied by the execution layer
        when actions are dispatched. This method exists so that internal
        auto-closes (DTE, stops, expiry cleanup) have a consistent path.
        """
        cashflow = 0.0
        for leg in position.legs:
            if isinstance(leg, StockLeg):
                cashflow += leg.current_price * leg.quantity
            elif isinstance(leg, OptionLeg):
                # closing means the inverse trade of what opened it
                cashflow += leg.current_premium * (-leg.quantity) * leg.shares_per_contract
        self.cash += cashflow
        position.realized_pnl = cashflow + position.entry_cashflow
        position.closed_at = snapshot.date
        position.tags.setdefault("close_reason", reason)
        self._move_to_closed(position)
        return cashflow

    def _move_to_closed(self, position: Position) -> None:
        if position in self.positions:
            self.positions.remove(position)
        self.closed_positions.append(position)
        if self.on_position_closed is not None:
            try:
                self.on_position_closed(position)
            except Exception:
                # Callback failures must not corrupt portfolio state.
                logger.exception(
                    "on_position_closed callback failed for %s", position.id
                )
