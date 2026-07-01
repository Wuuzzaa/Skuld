"""
Benchmark tracker — buys the benchmark symbol on day 1 and tracks total
return (dividend-reinvested proxy: use day_close changes).

Kap. 8.4.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from src.backtesting.data.snapshot import MarketSnapshot


@dataclass
class BenchmarkTracker:
    symbol: str = "SPY"
    initial_cash: float = 100_000.0
    entry_price: Optional[float] = None
    shares: float = 0.0
    _series: list[dict] = field(default_factory=list)

    def observe(self, d: date, snapshot: MarketSnapshot) -> None:
        stock = snapshot.get_stock(self.symbol)
        if stock is None or stock.day_close <= 0:
            # Missing benchmark data for this day -> skip, but still stamp
            # last observed value for continuity.
            if self._series:
                last = self._series[-1]
                self._series.append({
                    "date": d, "price": last["price"], "value": last["value"],
                })
            return
        price = stock.day_close
        if self.entry_price is None:
            self.entry_price = price
            self.shares = self.initial_cash / price
        # Simplistic dividend handling: credit last_dividend * shares when
        # today == last_dividend_date, then reinvest at close.
        if stock.last_dividend and stock.last_dividend_date == d:
            div_cash = stock.last_dividend * self.shares
            self.shares += div_cash / price
        self._series.append({
            "date": d, "price": price, "value": self.shares * price,
        })

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self._series)
