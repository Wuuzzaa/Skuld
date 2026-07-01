"""
ResultsCollector — accumulates trade / position / daily logs during a run.
Results — the final materialized object returned to the frontend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from uuid import UUID, uuid4

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
        self._closed_positions_seen: set[UUID] = set()

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
        for p in portfolio.closed_positions:
            if p.id in self._closed_positions_seen:
                continue
            self._closed_positions_seen.add(p.id)

    # ── Finalisation ─────────────────────────────────────────────────────

    def finalize(self) -> Results:
        from src.backtesting.results.metrics import MetricsCalculator

        trade_df = pd.DataFrame(self._trades)
        daily_df = pd.DataFrame(self._dailies)
        position_df = self._build_position_log()
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
            position_log=position_df,
            benchmark_series=benchmark_df,
            metrics=metrics.__dict__ if hasattr(metrics, "__dict__") else dict(metrics),
        )

    def _build_position_log(self) -> pd.DataFrame:
        # The engine hands us dailies + trades but not the closed-position
        # objects directly, so we reconstruct summaries via the trade log.
        if not self._trades:
            return pd.DataFrame()
        trades = pd.DataFrame(self._trades)
        if "position_id" not in trades.columns:
            return pd.DataFrame()

        rows = []
        for pos_id, group in trades.groupby("position_id"):
            open_rows = group[group["type"].str.startswith("open", na=False)]
            close_rows = group[group["type"].str.startswith("close", na=False)]
            symbol = group["symbol"].iloc[0] if "symbol" in group.columns else ""
            open_date = group["date"].min()
            close_date = close_rows["date"].max() if not close_rows.empty else None
            realized = 0.0
            for _, row in group.iterrows():
                qty = row.get("quantity", 0) or 0
                if row["type"].startswith("open_stock"):
                    realized -= row.get("price", 0) * qty
                elif row["type"].startswith("close_stock"):
                    realized += row.get("price", 0) * qty
                elif row["type"].startswith("open_option"):
                    realized -= (
                        row.get("premium", 0) * qty * 100
                    )
                elif row["type"].startswith("close_option"):
                    realized += (
                        row.get("premium", 0) * qty * 100
                    )
                realized -= row.get("commission", 0) or 0
            rows.append({
                "position_id": pos_id,
                "symbol": symbol,
                "open_date": open_date,
                "close_date": close_date,
                "realized_pnl": realized,
                "holding_days": (
                    (close_date - open_date).days
                    if close_date is not None and open_date is not None else None
                ),
                "close_reason": (
                    close_rows["reason"].iloc[-1]
                    if "reason" in close_rows.columns and not close_rows.empty else None
                ),
            })
        return pd.DataFrame(rows)


def _as_config_dict(config) -> dict:
    if config is None:
        return {}
    if isinstance(config, dict):
        return dict(config)
    if hasattr(config, "__dict__"):
        return {k: v for k, v in config.__dict__.items() if not k.startswith("_")}
    return {}
