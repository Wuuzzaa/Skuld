"""
Slippage model — OI-based (default) with fixed-pct fallback.

Kap. 7.2 defaults:
  stocks:                       0.05%
  options OI > 1000:            0.5%
  options OI 100-1000:          1.0%
  options OI < 100:             3.0% (or reject if config.reject_illiquid)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


def oi_based_slippage(open_interest: int) -> float:
    if open_interest > 1000:
        return 0.005
    if open_interest >= 100:
        return 0.010
    return 0.030


@dataclass
class SlippageModel:
    mode: Literal["oi", "fixed"] = "oi"
    fixed_pct: float = 0.005
    reject_illiquid: bool = False

    def option_slippage_pct(self, open_interest: int) -> Optional[float]:
        """Return slippage fraction, or None if the order should be rejected."""
        if self.mode == "fixed":
            return self.fixed_pct
        if self.reject_illiquid and open_interest < 100:
            return None
        return oi_based_slippage(open_interest)

    def stock_slippage_pct(self) -> float:
        return 0.0005 if self.mode == "oi" else self.fixed_pct
