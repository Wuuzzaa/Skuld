"""
Streamlit page — Backtesting Framework V1 (backtest.md Kap. 9).

Five tabs: Setup, Performance, Trades, Symbols, Export.

Runs synchronously in the Streamlit request context per Kap. 2.3 (V1
consciously stays out of the async/worker land).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Import the backtesting framework. This also triggers strategy auto-registration
# via `src/backtesting/strategies/__init__.py`.
from src.backtesting import (
    Portfolio,
    UniverseSpec,
    registry,
    run as run_backtest,
)
from src.backtesting.data.fields import FIELD_CATEGORIES
from src.backtesting.data.universe import UniverseFilter
from src.backtesting.data.validator import validate_universe_and_range
from src.backtesting.engine.engine import RunConfig
from src.backtesting.results.export import export_csv, export_json
from src.backtesting.results.storage import list_runs, load_results, save_results
from src.backtesting.strategies.params import (
    BoolParam, ChoiceParam, NumericParam, TupleParam,
)

logger = logging.getLogger(os.path.basename(__file__))

st.title("Backtesting Framework")
st.caption(
    "Strategy-neutral EOD backtester. V1 — see `backtest.md` for scope and "
    "limitations."
)

tab_setup, tab_perf, tab_trades, tab_symbols, tab_export = st.tabs(
    ["Setup", "Performance", "Trades", "Symbols", "Export"]
)


# ── State bootstrap ──────────────────────────────────────────────────────

if "backtest_results" not in st.session_state:
    st.session_state.backtest_results = None
if "backtest_progress" not in st.session_state:
    st.session_state.backtest_progress = None


# ── Helpers ──────────────────────────────────────────────────────────────

def _render_param_form(strategy_cls) -> dict:
    """Auto-generate widgets for a strategy's declarative params."""
    values: dict = {}
    specs = strategy_cls.params.specs()
    for name, param in specs.items():
        label = param.label or name.replace("_", " ").title()
        if isinstance(param, NumericParam):
            step = param.step or (0.05 if isinstance(param.default, float) else 1)
            if param.range:
                lo, hi = param.range
                values[name] = st.number_input(
                    label, min_value=float(lo), max_value=float(hi),
                    value=float(param.default), step=float(step),
                    key=f"param_{name}",
                    help=param.description,
                )
            else:
                values[name] = st.number_input(
                    label, value=float(param.default), step=float(step),
                    key=f"param_{name}",
                    help=param.description,
                )
        elif isinstance(param, TupleParam):
            lo_default, hi_default = param.default
            c1, c2 = st.columns(2)
            with c1:
                lo = st.number_input(f"{label} (from)", value=float(lo_default),
                                     key=f"param_{name}_lo")
            with c2:
                hi = st.number_input(f"{label} (to)", value=float(hi_default),
                                     key=f"param_{name}_hi")
            values[name] = (lo, hi)
        elif isinstance(param, ChoiceParam):
            values[name] = st.selectbox(
                label, options=param.choices,
                index=param.choices.index(param.default)
                if param.default in param.choices else 0,
                key=f"param_{name}",
                help=param.description,
            )
        elif isinstance(param, BoolParam):
            values[name] = st.checkbox(
                label, value=bool(param.default), key=f"param_{name}",
                help=param.description,
            )
        else:
            values[name] = st.text_input(
                label, value=str(param.default), key=f"param_{name}",
                help=param.description,
            )
    return values


def _render_universe_setup() -> UniverseSpec:
    mode = st.radio(
        "Universe mode", options=["static", "dynamic"], horizontal=True,
        key="universe_mode",
    )
    if mode == "static":
        symbols_str = st.text_area(
            "Symbols (comma or newline separated)",
            value="SPY, QQQ, AAPL, MSFT",
            key="static_symbols",
        )
        symbols = [
            s.strip().upper()
            for s in symbols_str.replace("\n", ",").split(",")
            if s.strip()
        ]
        return UniverseSpec(mode="static", symbols=symbols)

    st.markdown("**Dynamic universe filter**")
    criteria: list[str] = []
    for category, fields in FIELD_CATEGORIES.items():
        with st.expander(category, expanded=False):
            for f in fields:
                use = st.checkbox(
                    f"Filter on {f.label}", key=f"filt_use_{f.key}",
                )
                if not use:
                    continue
                if f.dtype in ("float", "int"):
                    op = st.selectbox(
                        f"Operator for {f.label}",
                        options=[">", ">=", "<", "<=", "=="],
                        key=f"filt_op_{f.key}",
                    )
                    val = st.number_input(
                        f"Value for {f.label}", value=0.0, key=f"filt_val_{f.key}",
                    )
                    criteria.append(f"{f.key} {op} {val}")
                elif f.dtype == "str":
                    val = st.text_input(
                        f"Value for {f.label}", key=f"filt_val_{f.key}",
                    )
                    if val:
                        criteria.append(f'{f.key} == "{val}"')

    rank_by = st.selectbox(
        "Rank by",
        options=[""] + [f.key for grp in FIELD_CATEGORIES.values() for f in grp
                        if f.dtype in ("float", "int")],
        key="rank_by",
    )
    top_n = int(st.number_input("Top N", min_value=1, max_value=500,
                                value=20, step=1, key="top_n"))
    rebalance = st.selectbox(
        "Rebalance", options=["daily", "weekly", "monthly"], key="rebalance",
    )
    return UniverseSpec(
        mode="dynamic",
        filter=UniverseFilter(
            criteria=criteria,
            rank_by=rank_by or None,
            top_n=top_n,
        ),
        rebalance=rebalance,  # type: ignore[arg-type]
    )


# ── Setup tab ────────────────────────────────────────────────────────────

with tab_setup:
    st.subheader("Strategy")
    strat_names = registry.list_names()
    if not strat_names:
        st.error("No strategies registered. Something is wrong with the imports.")
        st.stop()

    strat_name = st.selectbox("Strategy", options=strat_names, key="strategy_name")
    strategy_cls = registry.get(strat_name)
    st.caption(getattr(strategy_cls, "description", ""))

    with st.expander("Strategy parameters", expanded=True):
        param_values = _render_param_form(strategy_cls)

    st.subheader("Universe")
    universe_spec = _render_universe_setup()

    st.subheader("Timeframe")
    # Default timeframe: last 2 months as requested
    today = date.today()
    default_start = today - timedelta(days=60)
    default_end = today
    c1, c2 = st.columns(2)
    with c1:
        start_d = st.date_input("Start date", value=default_start, key="start_d")
    with c2:
        end_d = st.date_input("End date", value=default_end, key="end_d")

    st.subheader("Engine")
    c1, c2, c3 = st.columns(3)
    with c1:
        initial_cash = st.number_input(
            "Initial cash ($)", min_value=1_000.0, value=100_000.0,
            step=1_000.0, key="initial_cash",
        )
        slippage_mode = st.selectbox("Slippage mode", options=["oi", "fixed"],
                                     key="slippage_mode")
    with c2:
        dte_close = st.number_input(
            "Auto-close options at DTE <= ", min_value=0, max_value=45,
            value=7, step=1, key="dte_close",
        )
        benchmark = st.text_input("Benchmark symbol", value="SPY",
                                  key="benchmark")
    with c3:
        margin_rate = st.number_input(
            "Margin interest rate (%/yr)", min_value=0.0, max_value=25.0,
            value=7.0, step=0.25, key="margin_rate",
        ) / 100
        reject_illiq = st.checkbox("Reject illiquid option orders (OI < 100)",
                                   value=False, key="reject_illiq")

    if st.button("Run backtest", type="primary", key="run_btn"):
        # Validate first
        symbols_for_check = (
            universe_spec.symbols if universe_spec.mode == "static" else []
        )
        if symbols_for_check:
            with st.spinner("Validating universe & date range..."):
                val = validate_universe_and_range(
                    symbols_for_check, start_d, end_d,
                )
            for w in val.warnings:
                st.warning(w)
            for e in val.errors:
                st.error(e)
            if not val.ok:
                st.stop()
            if val.available_from:
                st.info(
                    f"DB coverage: {val.available_from} → {val.available_to}",
                )

        # Instantiate the strategy and inject params
        strategy = strategy_cls()
        for k, v in param_values.items():
            try:
                strategy.params.set(k, v)
            except KeyError:
                pass

        cfg = RunConfig(
            initial_cash=float(initial_cash),
            dte_close_threshold=int(dte_close),
            slippage_mode=slippage_mode,
            benchmark_symbol=benchmark,
            margin_interest_rate=float(margin_rate),
            reject_illiquid=bool(reject_illiq),
        )

        progress_bar = st.progress(0, text="Starting backtest...")
        status_area = st.empty()

        def _cb(current: int, total: int, d: date, portfolio: Portfolio) -> None:
            pct = int(current / total * 100)
            progress_bar.progress(pct, text=f"Day {current}/{total} — {d}")
            status_area.markdown(
                f"**{d}** — equity: `${portfolio.equity:,.0f}` — "
                f"open positions: `{len(portfolio.open_positions)}`"
            )

        t0 = time.time()
        try:
            results = run_backtest(
                strategy=strategy,
                universe_spec=universe_spec,
                start_date=start_d,
                end_date=end_d,
                config=cfg,
                progress_callback=_cb,
            )
        except Exception as e:
            st.error(f"Backtest failed: {e}")
            logger.exception("Backtest failed")
            st.stop()
        finally:
            progress_bar.empty()
            status_area.empty()

        elapsed = time.time() - t0
        st.success(f"Backtest complete in {elapsed:.1f}s")
        try:
            saved = save_results(results)
            st.caption(f"Results saved to: `{saved}`")
        except Exception as e:
            logger.warning("Could not save results: %s", e)
        st.session_state.backtest_results = results

    st.markdown("---")
    st.subheader("Load saved run")
    saved_runs = list_runs()
    if saved_runs:
        options = {
            f"{c.get('strategy_name', '?')}  "
            f"({c.get('start_date', '?')} → {c.get('end_date', '?')})  "
            f"— {c.get('run_id', '')[:8]}": c["run_id"]
            for c in saved_runs
        }
        choice = st.selectbox("Saved runs", options=list(options.keys()),
                              key="load_run")
        if st.button("Load", key="load_btn"):
            try:
                st.session_state.backtest_results = load_results(options[choice])
                st.success(f"Loaded run {options[choice]}")
            except Exception as e:
                st.error(f"Load failed: {e}")


# ── Performance tab ──────────────────────────────────────────────────────

def _render_metric_cards(metrics: dict) -> None:
    def fmt_pct(v):
        return f"{v * 100:.1f}%" if isinstance(v, (int, float)) and v is not None else "—"

    def fmt_num(v, d=2):
        return f"{v:.{d}f}" if isinstance(v, (int, float)) and v is not None else "—"

    def fmt_dol(v):
        return f"${v:,.0f}" if isinstance(v, (int, float)) and v is not None else "—"

    cols = st.columns(4)
    cols[0].metric("Total Return", fmt_pct(metrics.get("total_return")))
    cols[1].metric("CAGR", fmt_pct(metrics.get("cagr")))
    cols[2].metric("Sharpe", fmt_num(metrics.get("sharpe")))
    cols[3].metric("Max DD", fmt_pct(metrics.get("max_drawdown_pct")))

    cols = st.columns(4)
    cols[0].metric("Win Rate", fmt_pct(metrics.get("win_rate")))
    cols[1].metric("Profit Factor", fmt_num(metrics.get("profit_factor")))
    cols[2].metric("# Trades", metrics.get("n_trades", 0))
    cols[3].metric("Expectancy", fmt_dol(metrics.get("expectancy")))

    cols = st.columns(4)
    cols[0].metric("Volatility", fmt_pct(metrics.get("annualized_vol")))
    cols[1].metric("Sortino", fmt_num(metrics.get("sortino")))
    cols[2].metric("Calmar", fmt_num(metrics.get("calmar")))
    cols[3].metric("Alpha", fmt_pct(metrics.get("alpha")))


with tab_perf:
    r = st.session_state.backtest_results
    if r is None:
        st.info("Run a backtest first.")
    else:
        _render_metric_cards(r.metrics)

        daily = r.daily_log
        bench = r.benchmark_series
        if not daily.empty:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=daily["date"], y=daily["equity"], mode="lines", name="Strategy",
            ))
            if bench is not None and not bench.empty:
                fig.add_trace(go.Scatter(
                    x=bench["date"], y=bench["value"], mode="lines",
                    name=f"Benchmark ({r.config.get('benchmark_symbol', 'SPY')})",
                ))
            fig.update_layout(
                title="Equity curve vs benchmark",
                yaxis_title="Portfolio value ($)",
                xaxis_title="Date",
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)

            eq = daily.set_index("date")["equity"].astype(float)
            dd = (eq - eq.cummax()) / eq.cummax()
            fig_dd = go.Figure(go.Scatter(x=dd.index, y=dd, mode="lines",
                                          line=dict(color="crimson")))
            fig_dd.update_layout(
                title="Drawdown", yaxis_tickformat=".0%",
                xaxis_title="Date", yaxis_title="Drawdown",
            )
            st.plotly_chart(fig_dd, use_container_width=True)


# ── Trades tab ───────────────────────────────────────────────────────────

with tab_trades:
    r = st.session_state.backtest_results
    if r is None:
        st.info("Run a backtest first.")
    elif r.trade_log is None or r.trade_log.empty:
        st.info("No trades were executed.")
    else:
        st.dataframe(r.trade_log, use_container_width=True, height=500)

        if not r.position_log.empty:
            st.subheader("Closed positions")
            st.dataframe(r.position_log, use_container_width=True, height=400)


# ── Symbols tab ──────────────────────────────────────────────────────────

with tab_symbols:
    r = st.session_state.backtest_results
    if r is None or r.trade_log is None or r.trade_log.empty:
        st.info("No trade data yet.")
    else:
        pos = r.position_log
        if pos.empty:
            st.info("No closed positions yet.")
        else:
            by_symbol = (
                pos.groupby("symbol")
                .agg(
                    n_trades=("position_id", "count"),
                    total_pnl=("realized_pnl", "sum"),
                    avg_pnl=("realized_pnl", "mean"),
                    win_rate=("realized_pnl",
                              lambda x: (x > 0).sum() / len(x) if len(x) else None),
                )
                .sort_values("total_pnl", ascending=False)
                .reset_index()
            )
            total = by_symbol["total_pnl"].sum()
            if total != 0:
                by_symbol["contribution_pct"] = by_symbol["total_pnl"] / total
            st.dataframe(by_symbol, use_container_width=True)


# ── Export tab ───────────────────────────────────────────────────────────

with tab_export:
    r = st.session_state.backtest_results
    if r is None:
        st.info("Run a backtest first.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "Trade log (CSV)",
                data=export_csv(r.trade_log),
                file_name=f"trades_{r.run_id}.csv",
                mime="text/csv",
            )
        with c2:
            st.download_button(
                "Daily log (CSV)",
                data=export_csv(r.daily_log),
                file_name=f"daily_{r.run_id}.csv",
                mime="text/csv",
            )
        with c3:
            st.download_button(
                "Position log (CSV)",
                data=export_csv(r.position_log),
                file_name=f"positions_{r.run_id}.csv",
                mime="text/csv",
            )

        st.download_button(
            "Metrics (JSON)",
            data=export_json(r.metrics),
            file_name=f"metrics_{r.run_id}.json",
            mime="application/json",
        )
        st.download_button(
            "Config (JSON)",
            data=export_json(r.config),
            file_name=f"config_{r.run_id}.json",
            mime="application/json",
        )
