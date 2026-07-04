"""
Tests for the Buy and Hold strategy.
"""

from datetime import date
from src.backtesting import registry
from src.backtesting.data.universe import UniverseSpec
from src.backtesting.engine.engine import RunConfig, run as run_backtest
from tests.backtesting.test_smoke import _SyntheticPreloader

def test_buy_and_hold_flow():
    # Ensure strategy is registered
    strategy_cls = registry.get("Buy and Hold")
    assert strategy_cls is not None
    strategy = strategy_cls()
    
    # Define a 5-day trading week (Mon-Fri)
    # January 5th, 2026 is a Monday
    start = date(2026, 1, 5)
    end = date(2026, 1, 9)
    
    universe = UniverseSpec(mode="static", symbols=["AAPL"])
    cfg = RunConfig(initial_cash=100_000.0)
    # Using the synthetic preloader to avoid DB dependency
    preloader = _SyntheticPreloader(["AAPL"])
    
    results = run_backtest(
        strategy=strategy,
        universe_spec=universe,
        start_date=start,
        end_date=end,
        config=cfg,
        preloader=preloader,
    )
    
    assert results is not None
    
    # 1. Verify trades
    trades = results.trade_log
    assert not trades.empty
    
    # Should have at least one buy and one sell
    buy_trades = trades[trades["type"].str.contains("open", case=False)]
    sell_trades = trades[trades["type"].str.contains("close", case=False)]
    
    assert len(buy_trades) == 1
    assert len(sell_trades) == 1
    
    # Buy on first day
    assert buy_trades.iloc[0]["date"] == start
    assert buy_trades.iloc[0]["symbol"] == "AAPL"
    assert buy_trades.iloc[0]["quantity"] == 100
    assert buy_trades.iloc[0]["reason"] == "initial_buy"
    
    # Sell on last day
    assert sell_trades.iloc[0]["date"] == end
    assert sell_trades.iloc[0]["symbol"] == "AAPL"
    assert sell_trades.iloc[0]["reason"] == "end_of_backtest"

    # 2. Verify daily log
    dailies = results.daily_log
    assert len(dailies) == 5 # 5 trading days
    
    # Middle days should have 1 open position
    for i in range(1, 4): # Days 1, 2, 3 (Indices for Tue, Wed, Thu)
        assert dailies.iloc[i]["open_positions"] == 1
        
    # Last day EOD should have 0 open positions because we closed it in on_day
    assert dailies.iloc[4]["open_positions"] == 0
