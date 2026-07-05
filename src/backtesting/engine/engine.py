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
    symbols_to_preload = None
    if universe_spec.mode == "static":
        symbols_to_preload = list(set(universe_spec.symbols or []) | {cfg.benchmark_symbol}) if cfg.benchmark_symbol else universe_spec.symbols

    preloader = preloader or SmartPreloader(
        symbols=symbols_to_preload,
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
    # Wire the portfolio's close-callback into the collector so every path
    # that closes a position (executor, DTE-close, stop-order, expiry) ends
    # up in `results.position_log` with the P&L the portfolio actually
    # booked — no reconstruction from trade-log.
    portfolio.on_position_closed = collector.on_position_closed
    # Inject collector into strategy for logging details
    object.__setattr__(strategy, "_logger", collector)

    days = trading_days(start_date, end_date)
    if not days:
        logger.warning("No trading days between %s and %s", start_date, end_date)
        return collector.finalize()

    logger.debug("Total trading days to process: %d", len(days))
    strategy.on_init(cfg)

    for i, d in enumerate(days):
        logger.debug("--- Processing Day %d/%d: %s ---", i + 1, len(days), d)
        symbols_today = universe.resolve(d)
        
        # Ensure benchmark is loaded even if not in universe
        load_symbols = symbols_today
        if load_symbols is not None and cfg.benchmark_symbol:
            load_symbols = list(set(load_symbols) | {cfg.benchmark_symbol})
            
        snapshot = preloader.get_snapshot(d, symbols=load_symbols)

        # Inject flag for last day if useful for strategies
        is_last_day = (i == len(days) - 1)
        if is_last_day:
            object.__setattr__(snapshot, "is_last_day", True)
        else:
            object.__setattr__(snapshot, "is_last_day", False)

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
                        # Also mirror to detail log for consistent transaction tracking.
                        # Portfolio is queried AFTER the trade so quantity_position
                        # reflects the post-action leg balance (close → 0).
                        _record_trade_as_detail(collector, d, entry, portfolio)
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


def _record_trade_as_detail(
    collector, d: date, entry: dict, portfolio: Portfolio
) -> None:
    """Helper to mirror a trade-log entry into the detail-log with specific fields.

    Emits one detail row per trade-log entry (one per leg for multi-leg orders).

    Two quantity columns are recorded:
      * `quantity_change`   — signed delta from this action
                              (positive = buy/add, negative = sell/close).
      * `quantity_position` — remaining balance of the affected leg AFTER this
                              action (0 for a full close). For stock legs the
                              leg is identified by symbol within the position;
                              for option legs by `option_osi`.
    """
    from src.backtesting.engine.portfolio import OptionLeg, StockLeg

    t = entry.get("type", "")
    symbol = entry.get("symbol", "")
    qty = entry.get("quantity", 0) or 0
    price = entry.get("price") or entry.get("premium", 0)
    comm = entry.get("commission", 0)

    # Consistent logic now that executor uses trade_qty (positive = buy, negative = sell)
    multiplier = 100 if "option" in t else 1
    val = price * abs(qty) * multiplier

    if qty > 0:
        cost = val
        proceeds = 0.0
    else:
        cost = 0.0
        proceeds = val

    # Post-action leg balance: search the position that owns this trade.
    quantity_position = _resolve_leg_quantity_after_action(
        portfolio, entry, symbol
    )

    collector.record_detail(
        d, symbol,
        message=f"Transaction: {t} ({entry.get('reason', 'n/a')})",
        price=price,
        quantity_change=qty,
        quantity_position=quantity_position,
        cost=cost,
        proceeds=proceeds,
        commission=comm,
    )


def _resolve_leg_quantity_after_action(
    portfolio: Portfolio, entry: dict, symbol: str
) -> int:
    """Return the current quantity of the leg touched by a trade-log entry.

    Looks up the position by `position_id` (open or closed) and picks the
    matching leg:
      * option legs → matched by `option_osi`,
      * stock  legs → matched by `symbol`.

    Returns 0 if the position/leg no longer exists (full close).
    """
    from src.backtesting.engine.portfolio import OptionLeg, StockLeg

    pos_id = entry.get("position_id")
    if not pos_id:
        return 0

    # Positions container holds open positions; closed positions moved to
    # closed_positions when the last leg was removed. We search both.
    all_positions = list(portfolio.positions) + list(portfolio.closed_positions)
    position = next(
        (p for p in all_positions if str(p.id) == str(pos_id)),
        None,
    )
    if position is None:
        return 0

    t = entry.get("type", "")
    if "option" in t:
        osi = entry.get("option_osi")
        for leg in position.legs:
            if isinstance(leg, OptionLeg) and leg.option_osi == osi:
                return int(leg.quantity)
        return 0

    # stock leg
    for leg in position.legs:
        if isinstance(leg, StockLeg) and leg.symbol == symbol:
            return int(leg.quantity)
    return 0
