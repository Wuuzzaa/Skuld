"""
Commission calculator — IB-tiered defaults, fully configurable.

Kap. 7.3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CommissionConfig:
    option_per_contract: float = 0.65
    option_min_order: float = 1.00
    stock_per_share: float = 0.005
    stock_min_order: float = 1.00
    stock_max_pct: float = 0.01
    regulatory_per_option: float = 0.05


class CommissionCalculator:
    def __init__(self, config: CommissionConfig | None = None):
        self.config = config or CommissionConfig()

    def option_commission(self, contracts: int) -> float:
        c = self.config
        contracts = abs(int(contracts))
        if contracts == 0:
            return 0.0
        raw = contracts * c.option_per_contract
        base = max(raw, c.option_min_order)
        return base + contracts * c.regulatory_per_option

    def stock_commission(self, shares: int, price: float) -> float:
        c = self.config
        shares = abs(int(shares))
        if shares == 0:
            return 0.0
        raw = shares * c.stock_per_share
        base = max(raw, c.stock_min_order)
        cap = shares * price * c.stock_max_pct
        return min(base, cap) if cap > 0 else base
