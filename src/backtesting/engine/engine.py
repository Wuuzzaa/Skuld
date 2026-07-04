"""
Main engine loop.

`run(strategy, universe, start, end, initial_cash, config)` returns a
`Results` object populated by the ResultsCollector across the day-by-day
loop described in backtest.md Kap. 4.1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from src.backtesting.data.loader import SmartPreloader
from src.backtesting.data.snapshot import MarketSnapshot
from src.backtesting.data.universe import Universe, UniverseSpec
from src.backtesting.engine.actions import Action
from src.backtesting.engine.calendar import trading_days
from src.backtesting.engine.portfolio import Portfolio

logger = logging.getLogger(__name__)


@dataclass
class RunConfig:
    initial_cash: float = 100_000.0
    dte_close_threshold: Optional[int] = 7  # auto-close options at <= X DTE
    slippage_mode: str = "oi"  # "oi" or "fixed"
    slippage_fixed_pct: float = 0.005
    commission_config: dict = field(default_factory=dict)
    margin_interest_rate: float = 0.07  # yearly
    borrow_fee_default: float = 0.01
    benchmark_symbol: str = "SPY"
    execution_timing: str = "moc"  # "moc" or "next_open"
    reject_illiquid: bool = False  # if True, reject option orders with OI<100
    ram_warn_gb: float = 4.0


def run(
    strategy,
    universe_spec: UniverseSpec,
    start_date: date,
    end_date: date,
    config: Optional[RunConfig] = None,
    preloader: Optional[SmartPreloader] = None,
    progress_callback: Optional[Callable[[int, int, date, Portfolio], None]] = None,
):
    """
    Execute the backtest and return a `Results` object.

    Loosely follows backtest.md Kap. 4.1. Split into small internal helpers
    for readability + testability.
    """
    from src.backtesting.execution.executor import Executor
    from src.backtesting.results.collector import ResultsCollector
    from src.logger_config import setup_logging

    # Ensure debug logging to console as requested
    setup_logging(log_level=logging.DEBUG, component="engine", console_output=True)

    cfg = config or RunConfig()

    logger.debug("Starting backtest: strategy=%s, period=%s to %s, initial_cash=%.2f", 
                 getattr(strategy, 'name', 'unknown'), start_date, end_date, cfg.initial_cash)

    portfolio = Portfolio(
        cash=cfg.initial_cash,
        config={
            "dte_close_threshold": cfg.dte_close_threshold,
            "margin_interest_rate": cfg.margin_interest_rate,
            "borrow_fee_default": cfg.borrow_fee_default,
        },
    )

    universe = Universe(universe_spec)
    preloader = preloader or SmartPreloader(
        symbols=universe_spec.symbols if universe_spec.mode == "static" else None,
        fields=getattr(strategy, "preload_fields", [])
    )
    executor = Executor(cfg)
    collector = ResultsCollector(
        strategy_name=strategy.name,
        start_date=start_date,
        end_date=end_date,
        config=cfg,
        benchmark_symbol=cfg.benchmark_symbol,
    )

    days = trading_days(start_date, end_date)
    if not days:
        logger.warning("No trading days between %s and %s", start_date, end_date)
        return collector.finalize()

    logger.debug("Total trading days to process: %d", len(days))
    strategy.on_init(cfg)

    for i, d in enumerate(days):
        logger.debug("--- Processing Day %d/%d: %s ---", i + 1, len(days), d)
        symbols_today = universe.resolve(d)
        snapshot = preloader.get_snapshot(d, symbols=symbols_today or None)

        # ── 2. Automated maintenance ────────────────────────────────────
        logger.debug("Maintenance: MTM, Dividends, Splits, Expiries, DTE, Rolling")
        portfolio.mark_to_market(snapshot)
        portfolio.apply_dividends(snapshot)
        portfolio.apply_splits(snapshot)
        portfolio.apply_expiries(snapshot)
        portfolio.check_dte_close(snapshot)
        portfolio.check_rolling(snapshot, strategy)
        portfolio.check_stop_orders(snapshot)
        if symbols_today:
            portfolio.enforce_universe(snapshot, symbols_today)

        # ── 3. Strategy decision ────────────────────────────────────────
        compute_daily = getattr(strategy, "compute_daily", None)
        if callable(compute_daily):
            try:
                logger.debug("Calling strategy.compute_daily")
                compute_daily(snapshot, portfolio)
            except Exception as e:
                logger.exception("compute_daily failed on %s: %s", d, e)

        actions: list[Action] = []
        try:
            logger.debug("Calling strategy.on_day")
            result = strategy.on_day(snapshot, portfolio)
            if result:
                actions = list(result)
                logger.debug("Strategy produced %d actions", len(actions))
        except Exception as e:
            logger.exception("on_day failed on %s: %s", d, e)

        # ── 4. Execute actions ──────────────────────────────────────────
        for action in actions:
            try:
                logger.debug("Executing action: %s", action)
                trade_log = executor.execute(action, portfolio, snapshot)
                if trade_log:
                    logger.debug("Action resulted in %d trade entries", len(trade_log))
                    for entry in trade_log:
                        collector.record_trade(d, entry)
            except Exception as e:
                logger.exception("execution failed on %s: %s", d, e)

        # ── 5. Record end-of-day snapshot of the portfolio ──────────────
        logger.debug("Recording EOD snapshot")
        collector.record_day(d, portfolio, snapshot)

        if progress_callback is not None:
            try:
                progress_callback(i + 1, len(days), d, portfolio)
            except Exception:
                pass

    logger.debug("Backtest completed. Finalizing results.")
    return collector.finalize()
