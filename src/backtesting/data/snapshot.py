"""
MarketSnapshot: read-only view of the market at a specific EOD date.

The snapshot is the interface that strategies see. It exposes:
- `stocks`: dict[symbol -> StockData] with OHLC + indicators + fundamentals
- `chains`: dict[symbol -> OptionChain] with all option contracts for that symbol
- `universe`: list of symbols that are "active" today

Contains no look-ahead data — the loader is responsible for materializing
only fields that would have been visible at the target EOD date.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Option:
    """A single option contract at one point in time."""

    symbol: str
    option_osi: str
    contract_type: str  # "call" or "put"
    expiration_date: date
    strike: float
    day_close: float  # mid-proxy premium
    open_interest: int
    day_volume: int
    implied_volatility: Optional[float]
    delta: Optional[float]
    gamma: Optional[float]
    theta: Optional[float]
    vega: Optional[float]
    days_to_expiration: int
    shares_per_contract: int = 100

    @property
    def premium(self) -> float:
        return self.day_close

    @property
    def is_call(self) -> bool:
        return self.contract_type.lower() == "call"

    @property
    def is_put(self) -> bool:
        return self.contract_type.lower() == "put"


@dataclass
class OptionChain:
    """All option contracts for one underlying on one date."""

    symbol: str
    as_of: date
    calls: list[Option] = field(default_factory=list)
    puts: list[Option] = field(default_factory=list)

    def all(self) -> list[Option]:
        return self.calls + self.puts

    def by_expiration(self, expiration: date) -> list[Option]:
        return [o for o in self.all() if o.expiration_date == expiration]

    def find(
        self,
        *,
        contract_type: str,
        delta_target: Optional[float] = None,
        dte_range: Optional[tuple[int, int]] = None,
        strike_target: Optional[float] = None,
        min_open_interest: int = 0,
    ) -> Optional[Option]:
        """
        Pick the single best-matching option under the given constraints.

        Priority:
        - `delta_target`: minimize |delta - delta_target|
        - `strike_target`: minimize |strike - strike_target|
        Filter first on contract_type, dte_range, min_open_interest.
        """
        candidates = self.calls if contract_type.lower() == "call" else self.puts
        candidates = [c for c in candidates if c.open_interest >= min_open_interest]

        if dte_range is not None:
            lo, hi = dte_range
            candidates = [c for c in candidates if lo <= c.days_to_expiration <= hi]

        if not candidates:
            return None

        if delta_target is not None:
            candidates = [c for c in candidates if c.delta is not None]
            if not candidates:
                return None
            # For puts, delta is negative — compare on |delta|
            return min(candidates, key=lambda c: abs(abs(c.delta) - abs(delta_target)))

        if strike_target is not None:
            return min(candidates, key=lambda c: abs(c.strike - strike_target))

        return None


@dataclass
class StockData:
    """OHLC + indicators + fundamentals for one underlying on one date."""

    symbol: str
    as_of: date
    day_close: float
    day_open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None
    day_volume: Optional[int] = None
    live_stock_price: Optional[float] = None
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None
    historical_volatility_30d: Optional[float] = None
    earnings_date: Optional[date] = None
    days_to_earnings: Optional[int] = None
    last_dividend: Optional[float] = None
    last_dividend_date: Optional[date] = None
    dividend_growth_years: Optional[int] = None
    analyst_mean_target: Optional[float] = None
    # Free-form bag for extra fundamentals (loaded on-demand per strategy)
    extras: dict = field(default_factory=dict)


@dataclass
class MarketSnapshot:
    """
    Complete market view for one EOD date.

    Everything the strategy is allowed to see for its `on_day` decision.
    """

    date: date
    stocks: dict[str, StockData] = field(default_factory=dict)
    chains: dict[str, OptionChain] = field(default_factory=dict)
    universe: list[str] = field(default_factory=list)

    def get_stock(self, symbol: str) -> Optional[StockData]:
        return self.stocks.get(symbol)

    def get_chain(self, symbol: str) -> Optional[OptionChain]:
        return self.chains.get(symbol)

    def find_option(
        self,
        symbol: str,
        contract_type: str,
        *,
        delta_target: Optional[float] = None,
        dte_range: Optional[tuple[int, int]] = None,
        strike_target: Optional[float] = None,
        min_open_interest: int = 0,
    ) -> Optional[Option]:
        chain = self.get_chain(symbol)
        if chain is None:
            return None
        return chain.find(
            contract_type=contract_type,
            delta_target=delta_target,
            dte_range=dte_range,
            strike_target=strike_target,
            min_open_interest=min_open_interest,
        )
