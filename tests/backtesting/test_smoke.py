"""
Smoke tests: import every module, register all strategies, run a tiny
end-to-end backtest against a synthetic in-memory data source.

No DB is touched.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.backtesting import registry
from src.backtesting.data.snapshot import (
    MarketSnapshot, Option, OptionChain, StockData,
)
from src.backtesting.data.universe import UniverseSpec
from src.backtesting.engine.engine import RunConfig, run as run_backtest


class _SyntheticPreloader:
    """A tiny preloader that fabricates one snapshot per date."""

    def __init__(self, symbols: list[str]):
        self.symbols = symbols
        self._snapshots: dict[date, MarketSnapshot] = {}

    def get_snapshot(self, target_date: date, symbols=None) -> MarketSnapshot:
        if target_date not in self._snapshots:
            self._snapshots[target_date] = self._build(target_date)
        snap = self._snapshots[target_date]
        return snap


    def _build(self, d: date) -> MarketSnapshot:
        snap = MarketSnapshot(date=d)
        # Deterministic price walk so backtests are reproducible in CI
        seed = d.toordinal()
        for i, sym in enumerate(self.symbols):
            price = 100.0 + (seed % 20) + i * 5
            snap.stocks[sym] = StockData(
                symbol=sym, as_of=d, live_stock_price=price, day_close=price,
                iv_rank=40.0, historical_volatility_30d=0.25,
            )
            chain = OptionChain(symbol=sym, as_of=d)
            for k in range(-3, 4):
                strike = round(price + k * 5, 2)
                dte = 35
                exp = d + timedelta(days=dte)
                # Call
                chain.calls.append(Option(
                    symbol=sym, option_osi=f"{sym}C{strike}{d.isoformat()}",
                    contract_type="call",
                    expiration_date=exp, strike=strike,
                    day_close=max(0.10, price - strike + 2.5) if k <= 0 else 1.0,
                    open_interest=500, day_volume=100,
                    implied_volatility=0.30,
                    delta=max(0.05, 0.50 - k * 0.12),
                    gamma=0.02, theta=-0.05, vega=0.10,
                    days_to_expiration=dte,
                ))
                # Put
                chain.puts.append(Option(
                    symbol=sym, option_osi=f"{sym}P{strike}{d.isoformat()}",
                    contract_type="put",
                    expiration_date=exp, strike=strike,
                    day_close=max(0.10, strike - price + 2.5) if k >= 0 else 1.0,
                    open_interest=500, day_volume=100,
                    implied_volatility=0.30,
                    delta=min(-0.05, -0.50 + k * 0.12),
                    gamma=0.02, theta=-0.05, vega=0.10,
                    days_to_expiration=dte,
                ))
            snap.chains[sym] = chain
        snap.universe = list(self.symbols)
        return snap


def test_registry_has_v1_templates():
    names = registry.list_names()
    assert "Covered Call" in names
    assert "Cash-Secured Put" in names
    assert "Wheel" in names
    assert "Vertical Spread" in names
    assert "Iron Condor" in names


def test_snapshot_find_option():
    snap = _SyntheticPreloader(["SPY"]).get_snapshot(date(2026, 1, 15))
    opt = snap.find_option(
        "SPY", "put", delta_target=-0.30, dte_range=(20, 60),
    )
    assert opt is not None
    assert opt.symbol == "SPY"
    assert opt.contract_type == "put"


@pytest.mark.parametrize("strategy_name", [
    "Cash-Secured Put",
    "Vertical Spread",
    "Iron Condor",
])
def test_run_two_weeks_no_error(strategy_name):
    """Executing a real strategy for 10 trading days must not raise."""
    strategy_cls = registry.get(strategy_name)
    strategy = strategy_cls()

    start = date(2026, 1, 5)
    end = date(2026, 1, 19)

    universe = UniverseSpec(mode="static", symbols=["SPY"])
    cfg = RunConfig(
        initial_cash=100_000.0,
        dte_close_threshold=None,  # avoid interfering with 35 DTE test data
    )
    preloader = _SyntheticPreloader(["SPY"])
    results = run_backtest(
        strategy=strategy,
        universe_spec=universe,
        start_date=start,
        end_date=end,
        config=cfg,
        preloader=preloader,
    )
    assert results is not None
    assert results.run_id is not None
    # equity is defined for every trading day
    assert not results.daily_log.empty
    assert (results.daily_log["equity"] > 0).all()
