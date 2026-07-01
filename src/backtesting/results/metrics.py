"""
Performance metrics calculator (Kap. 8.2).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    total_return: Optional[float] = None
    cagr: Optional[float] = None
    max_drawdown_abs: Optional[float] = None
    max_drawdown_pct: Optional[float] = None
    max_drawdown_days: Optional[int] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    calmar: Optional[float] = None
    annualized_vol: Optional[float] = None
    # Trade stats
    n_trades: int = 0
    win_rate: Optional[float] = None
    avg_win: Optional[float] = None
    avg_loss: Optional[float] = None
    largest_win: Optional[float] = None
    largest_loss: Optional[float] = None
    profit_factor: Optional[float] = None
    avg_holding_days: Optional[float] = None
    expectancy: Optional[float] = None
    # Benchmark
    benchmark_total_return: Optional[float] = None
    alpha: Optional[float] = None
    beta: Optional[float] = None


class MetricsCalculator:
    def __init__(
        self,
        daily_df: pd.DataFrame,
        trade_df: pd.DataFrame,
        benchmark_df: Optional[pd.DataFrame] = None,
        risk_free_rate: float = 0.043,
    ):
        self.daily_df = daily_df.copy() if daily_df is not None else pd.DataFrame()
        self.trade_df = trade_df.copy() if trade_df is not None else pd.DataFrame()
        self.benchmark_df = (
            benchmark_df.copy() if benchmark_df is not None else pd.DataFrame()
        )
        self.rf = risk_free_rate

    def compute(self) -> PerformanceMetrics:
        m = PerformanceMetrics()
        if not self.daily_df.empty:
            self._compute_equity_metrics(m)
        if not self.trade_df.empty:
            self._compute_trade_metrics(m)
        if not self.benchmark_df.empty:
            self._compute_benchmark_metrics(m)
        return m

    # ── Equity-curve metrics ─────────────────────────────────────────────

    def _compute_equity_metrics(self, m: PerformanceMetrics) -> None:
        eq = self.daily_df.set_index("date")["equity"].astype(float)
        if len(eq) < 2:
            return
        start_val, end_val = float(eq.iloc[0]), float(eq.iloc[-1])
        m.total_return = (end_val / start_val - 1) if start_val > 0 else None

        # CAGR
        days = (eq.index[-1] - eq.index[0]).days
        years = max(days / 365.25, 1e-6)
        m.cagr = ((end_val / start_val) ** (1 / years) - 1) if start_val > 0 else None

        # Drawdown
        running_max = eq.cummax()
        dd_series = (eq - running_max) / running_max
        m.max_drawdown_pct = float(dd_series.min())
        m.max_drawdown_abs = float((eq - running_max).min())
        # Duration in trading days between peak and trough of max DD
        trough_idx = dd_series.idxmin()
        peak_idx = running_max.loc[:trough_idx].idxmax()
        m.max_drawdown_days = int((trough_idx - peak_idx).days) if peak_idx and trough_idx else None

        # Volatility, Sharpe, Sortino, Calmar (daily returns)
        rets = eq.pct_change().dropna()
        if not rets.empty:
            m.annualized_vol = float(rets.std() * math.sqrt(252))
            excess = rets - self.rf / 252
            std = float(rets.std())
            if std > 0:
                m.sharpe = float(excess.mean() / std * math.sqrt(252))
            downside = rets[rets < 0]
            if len(downside) > 0 and downside.std() > 0:
                m.sortino = float(excess.mean() / downside.std() * math.sqrt(252))
            if m.cagr is not None and m.max_drawdown_pct not in (None, 0):
                m.calmar = float(m.cagr / abs(m.max_drawdown_pct))

    # ── Trade-log metrics ────────────────────────────────────────────────

    def _compute_trade_metrics(self, m: PerformanceMetrics) -> None:
        df = self.trade_df
        m.n_trades = int(len(df))
        if "position_id" not in df.columns:
            return

        # Aggregate P&L per position using cashflow columns present in the log.
        pnl_by_pos: dict[str, float] = {}
        for _, row in df.iterrows():
            pid = row.get("position_id")
            if not pid:
                continue
            direction = row.get("type", "")
            qty = row.get("quantity", 0) or 0
            comm = row.get("commission", 0) or 0
            price = row.get("price", 0) or 0
            premium = row.get("premium", 0) or 0
            change = 0.0
            if direction == "open_stock":
                change = -price * qty
            elif direction == "close_stock":
                change = price * qty
            elif direction == "open_option":
                change = -premium * qty * 100
            elif direction == "close_option":
                change = premium * qty * 100
            change -= comm
            pnl_by_pos[pid] = pnl_by_pos.get(pid, 0.0) + change

        pnls = list(pnl_by_pos.values())
        if not pnls:
            return
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        m.win_rate = len(wins) / len(pnls) if pnls else None
        m.avg_win = float(np.mean(wins)) if wins else None
        m.avg_loss = float(np.mean(losses)) if losses else None
        m.largest_win = float(max(wins)) if wins else None
        m.largest_loss = float(min(losses)) if losses else None
        loss_abs = abs(sum(losses))
        m.profit_factor = float(sum(wins) / loss_abs) if loss_abs > 0 else None
        m.expectancy = float(np.mean(pnls))

    # ── Benchmark ────────────────────────────────────────────────────────

    def _compute_benchmark_metrics(self, m: PerformanceMetrics) -> None:
        b = self.benchmark_df.set_index("date")["value"].astype(float)
        if len(b) < 2:
            return
        m.benchmark_total_return = float(b.iloc[-1] / b.iloc[0] - 1) if b.iloc[0] > 0 else None
        # Alpha / Beta over daily returns
        eq = self.daily_df.set_index("date")["equity"].astype(float)
        joined = pd.concat({"eq": eq, "bench": b}, axis=1).dropna()
        if len(joined) < 3:
            return
        eq_rets = joined["eq"].pct_change().dropna()
        b_rets = joined["bench"].pct_change().dropna()
        common = eq_rets.index.intersection(b_rets.index)
        eq_rets = eq_rets.loc[common]
        b_rets = b_rets.loc[common]
        if b_rets.var() > 0:
            beta = float(eq_rets.cov(b_rets) / b_rets.var())
            m.beta = beta
            m.alpha = float(eq_rets.mean() * 252 - beta * b_rets.mean() * 252)
