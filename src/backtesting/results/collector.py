"""
ResultsCollector — accumulates trade / position / daily logs during a run.
Results — the final materialized object returned to the frontend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from uuid import uuid4

import pandas as pd

from src.backtesting.data.snapshot import MarketSnapshot
from src.backtesting.engine.portfolio import OptionLeg, Portfolio, StockLeg
from src.backtesting.results.benchmark import BenchmarkTracker

logger = logging.getLogger(__name__)


@dataclass
class Results:
    run_id: str
    strategy_name: str
    start_date: date
    end_date: date
    config: dict
    trade_log: pd.DataFrame
    daily_log: pd.DataFrame
    detail_log: pd.DataFrame
    position_log: pd.DataFrame
    benchmark_series: pd.DataFrame
    metrics: dict = field(default_factory=dict)


class ResultsCollector:
    def __init__(
        self,
        strategy_name: str,
        start_date: date,
        end_date: date,
        config,
        benchmark_symbol: str = "SPY",
    ):
        self.run_id = str(uuid4())
        self.strategy_name = strategy_name
        self.start_date = start_date
        self.end_date = end_date
        self.config = _as_config_dict(config)
        self.benchmark_symbol = benchmark_symbol
        self.benchmark = BenchmarkTracker(
            symbol=benchmark_symbol,
            initial_cash=getattr(config, "initial_cash", 100_000.0),
        )
        self._trades: list[dict] = []
        self._dailies: list[dict] = []
        self._details: list[dict] = []
        # Positions get recorded exactly once — when Portfolio._move_to_closed
        # fires the on_position_closed callback (wired by the engine). No more
        # reconstruction-from-trade-log downstream.
        self._closed_positions: list[dict] = []

    # ── Recording ────────────────────────────────────────────────────────

    def record_trade(self, d: date, entry: dict) -> None:
        entry = dict(entry)
        entry.setdefault("date", d)
        self._trades.append(entry)

    def record_day(
        self, d: date, portfolio: Portfolio, snapshot: MarketSnapshot
    ) -> None:
        self.benchmark.observe(d, snapshot)
        unrealized = sum(p.unrealized_pnl for p in portfolio.open_positions)
        self._dailies.append({
            "date": d,
            "cash": portfolio.cash,
            "equity": portfolio.equity,
            "margin_used": portfolio.margin_used,
            "buying_power": portfolio.buying_power,
            "open_positions": len(portfolio.open_positions),
            "unrealized_pnl": unrealized,
        })

    def record_detail(self, d: date, symbol: str, message: str, **kwargs) -> None:
        entry = {
            "date": d,
            "symbol": symbol,
            "message": message,
        }
        entry.update(kwargs)
        self._details.append(entry)

    def on_position_closed(self, position) -> None:
        """Called by Portfolio._move_to_closed the moment a position is
        moved out of `open_positions`. Snapshots the closed position into
        the position_log immediately — no rebuild-from-trades later, so
        Assignment / Expiry / DTE-Close paths all record real
        `realized_pnl` (previously they fell out of the log entirely)."""
        # Snapshot legs so late mutations (unlikely, defensive) can't
        # rewrite history.
        legs_snapshot = []
        for leg in list(position.legs):
            leg_kind = "stock" if isinstance(leg, StockLeg) else "option"
            legs_snapshot.append({
                "kind": leg_kind,
                "symbol": leg.symbol,
                "quantity": int(leg.quantity),
                "option_osi": getattr(leg, "option_osi", None),
                "strike": getattr(leg, "strike", None),
                "expiration_date": getattr(leg, "expiration_date", None),
            })
        self._closed_positions.append({
            "position_id": str(position.id),
            "symbol": position.symbol,
            "open_date": position.opened_at,
            "close_date": position.closed_at,
            "entry_cashflow": float(position.entry_cashflow),
            "realized_pnl": float(position.realized_pnl),
            "holding_days": (
                (position.closed_at - position.opened_at).days
                if position.closed_at is not None
                and position.opened_at is not None
                else None
            ),
            "close_reason": position.tags.get("close_reason"),
            "template": position.tags.get("template"),
            "legs_at_close": legs_snapshot,
        })

    # ── Finalisation ─────────────────────────────────────────────────────

    def finalize(self) -> Results:
        from src.backtesting.results.metrics import MetricsCalculator

        trade_df = pd.DataFrame(self._trades)
        daily_df = pd.DataFrame(self._dailies)
        detail_df = pd.DataFrame(self._details)
        position_df = pd.DataFrame(self._closed_positions)
        benchmark_df = self.benchmark.to_dataframe()

        metrics_calc = MetricsCalculator(
            daily_df=daily_df,
            trade_df=trade_df,
            benchmark_df=benchmark_df,
        )
        metrics = metrics_calc.compute()

        return Results(
            run_id=self.run_id,
            strategy_name=self.strategy_name,
            start_date=self.start_date,
            end_date=self.end_date,
            config=self.config,
            trade_log=trade_df,
            daily_log=daily_df,
            detail_log=detail_df,
            position_log=position_df,
            benchmark_series=benchmark_df,
            metrics=metrics.__dict__ if hasattr(metrics, "__dict__") else dict(metrics),
        )


def _as_config_dict(config) -> dict:
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    if hasattr(config, "__dict__"):
        return {k: v for k, v in config.__dict__.items() if not k.startswith("_")}
    return {}
