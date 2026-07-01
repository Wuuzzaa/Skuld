"""
Reg-T margin calculator (V1).

Kap. 7.4:
  Covered Call (Stock + Short Call):       0 (fully secured)
  Cash-Secured Put:                        Strike * 100 * Qty (cash reserve)
  Naked Short Put:                         20% * Underlying - OTM-Amount + Premium
  Naked Short Call:                        20% * Underlying - OTM-Amount + Premium
  Vertical Spread:                         Spread-Width * 100 * Qty
  Iron Condor:                             max(call-width, put-width) * 100 * Qty
  Long Stock on Margin:                    50% Initial / 25% Maintenance

Portfolio Margin (risk-based) is roadmap V2.
"""

from __future__ import annotations

from typing import Iterable

from src.backtesting.engine.portfolio import OptionLeg, Position, StockLeg


class RegTMarginCalculator:
    """
    Compute the *initial* margin a position ties up, given the current
    underlying price.
    """

    def position_margin(
        self, position: Position, underlying_prices: dict[str, float]
    ) -> float:
        legs = position.legs
        option_legs = [l for l in legs if isinstance(l, OptionLeg)]
        stock_legs = [l for l in legs if isinstance(l, StockLeg)]

        if not option_legs and not stock_legs:
            return 0.0

        # Covered call: long stock + short call in same symbol -> stock backs the call
        if self._is_covered_call(stock_legs, option_legs):
            return 0.0

        # Cash-secured put: short put + cash reserve, treated as strike * 100 * qty
        if self._is_cash_secured_put(stock_legs, option_legs):
            short_put = next(l for l in option_legs if l.is_put and l.is_short)
            return abs(short_put.quantity) * short_put.strike * short_put.shares_per_contract

        # Vertical spread: exactly one long + one short of same type, same expiry
        if self._is_vertical_spread(option_legs):
            widths = self._spread_widths(option_legs)
            qty = min(abs(l.quantity) for l in option_legs)
            return max(widths) * 100 * qty

        # Iron Condor: 4 legs — short + long call spread + short + long put spread
        if self._is_iron_condor(option_legs):
            call_legs = [l for l in option_legs if l.is_call]
            put_legs = [l for l in option_legs if l.is_put]
            call_width = self._spread_widths(call_legs)
            put_width = self._spread_widths(put_legs)
            qty = min(abs(l.quantity) for l in option_legs)
            return max(max(call_width, default=0), max(put_width, default=0)) * 100 * qty

        # Fall-through: sum of per-leg naked margins + 50% for long-on-margin stock
        total = 0.0
        for leg in option_legs:
            if leg.quantity < 0:
                underlying = underlying_prices.get(leg.symbol, leg.strike)
                total += self._naked_option_margin(leg, underlying)
        for leg in stock_legs:
            if leg.quantity > 0:
                # long stock on margin uses 50% initial
                total += 0.5 * leg.current_price * leg.quantity
        return total

    # ── Detectors ────────────────────────────────────────────────────────

    @staticmethod
    def _is_covered_call(stock_legs, option_legs) -> bool:
        if len(stock_legs) != 1 or len(option_legs) != 1:
            return False
        stock = stock_legs[0]
        option = option_legs[0]
        return (
            stock.quantity > 0
            and option.is_call
            and option.is_short
            and stock.quantity >= abs(option.quantity) * option.shares_per_contract
        )

    @staticmethod
    def _is_cash_secured_put(stock_legs, option_legs) -> bool:
        return (
            not stock_legs
            and len(option_legs) == 1
            and option_legs[0].is_put
            and option_legs[0].is_short
        )

    @staticmethod
    def _is_vertical_spread(option_legs) -> bool:
        if len(option_legs) != 2:
            return False
        a, b = option_legs
        same_type = a.contract_type == b.contract_type
        same_expiry = a.expiration_date == b.expiration_date
        one_of_each = (a.is_short and not b.is_short) or (b.is_short and not a.is_short)
        return same_type and same_expiry and one_of_each

    @staticmethod
    def _is_iron_condor(option_legs) -> bool:
        if len(option_legs) != 4:
            return False
        calls = [l for l in option_legs if l.is_call]
        puts = [l for l in option_legs if l.is_put]
        if len(calls) != 2 or len(puts) != 2:
            return False
        return (
            any(l.is_short for l in calls) and any(not l.is_short for l in calls)
            and any(l.is_short for l in puts) and any(not l.is_short for l in puts)
        )

    @staticmethod
    def _spread_widths(legs: Iterable[OptionLeg]) -> list[float]:
        strikes = sorted({l.strike for l in legs})
        if len(strikes) < 2:
            return []
        return [strikes[i + 1] - strikes[i] for i in range(len(strikes) - 1)]

    @staticmethod
    def _naked_option_margin(leg: OptionLeg, underlying: float) -> float:
        # Reg-T naked short: 20% of underlying - OTM amount + premium
        # (with a min floor of 10% * strike + premium — we use the higher of the two)
        contracts = abs(leg.quantity)
        multiplier = leg.shares_per_contract
        if leg.is_call:
            otm_amount = max(0.0, leg.strike - underlying)
        else:
            otm_amount = max(0.0, underlying - leg.strike)
        primary = (
            0.20 * underlying * multiplier
            - otm_amount * multiplier
            + leg.current_premium * multiplier
        )
        floor = 0.10 * leg.strike * multiplier + leg.current_premium * multiplier
        return max(primary, floor) * contracts
