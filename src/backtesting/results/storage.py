"""
File-based persistence for backtest runs (Kap. 8.3).

Layout under `data/backtest_runs/{run_id}/`:
    config.json
    metrics.json
    trade_log.parquet
    daily_log.parquet
    position_log.parquet
    benchmark.parquet

Parquet is preferred (uses pyarrow); falls back to CSV if pyarrow is missing.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


DEFAULT_RUNS_DIR = Path("data") / "backtest_runs"


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
    return str(o)


def _write_frame(df: pd.DataFrame, path: Path) -> None:
    if df is None or df.empty:
        df = pd.DataFrame()
    try:
        df.to_parquet(path.with_suffix(".parquet"), index=False)
    except Exception as e:
        logger.debug("Parquet write failed (%s); falling back to CSV", e)
        df.to_csv(path.with_suffix(".csv"), index=False)


def _read_frame(path_stem: Path) -> pd.DataFrame:
    for ext in (".parquet", ".csv"):
        p = path_stem.with_suffix(ext)
        if not p.exists():
            continue
        try:
            if ext == ".parquet":
                return pd.read_parquet(p)
            return pd.read_csv(p)
        except Exception as e:
            logger.warning("Failed to read %s (%s)", p, e)
    return pd.DataFrame()


def save_results(results, runs_dir: Optional[Path] = None) -> Path:
    """Serialize `Results` to disk. Returns the run directory."""
    root = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
    run_dir = root / results.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    with (run_dir / "config.json").open("w") as f:
        json.dump(
            {
                "run_id": results.run_id,
                "strategy_name": results.strategy_name,
                "start_date": results.start_date,
                "end_date": results.end_date,
                "config": results.config,
            },
            f, default=_json_default, indent=2,
        )
    with (run_dir / "metrics.json").open("w") as f:
        json.dump(results.metrics, f, default=_json_default, indent=2)

    _write_frame(results.trade_log, run_dir / "trade_log")
    _write_frame(results.daily_log, run_dir / "daily_log")
    _write_frame(results.position_log, run_dir / "position_log")
    _write_frame(results.detail_log, run_dir / "detail_log")
    _write_frame(results.benchmark_series, run_dir / "benchmark")

    logger.info("Saved backtest run to %s", run_dir)
    return run_dir


def load_results(run_id: str, runs_dir: Optional[Path] = None):
    """Rehydrate a Results-like SimpleNamespace from disk."""
    from types import SimpleNamespace

    root = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
    run_dir = root / run_id
    if not run_dir.exists():
        raise FileNotFoundError(run_dir)

    with (run_dir / "config.json").open() as f:
        cfg = json.load(f)
    with (run_dir / "metrics.json").open() as f:
        metrics = json.load(f)

    return SimpleNamespace(
        run_id=cfg.get("run_id", run_id),
        strategy_name=cfg.get("strategy_name"),
        start_date=cfg.get("start_date"),
        end_date=cfg.get("end_date"),
        config=cfg.get("config", {}),
        metrics=metrics,
        trade_log=_read_frame(run_dir / "trade_log"),
        daily_log=_read_frame(run_dir / "daily_log"),
        position_log=_read_frame(run_dir / "position_log"),
        detail_log=_read_frame(run_dir / "detail_log"),
        benchmark_series=_read_frame(run_dir / "benchmark"),
    )


def list_runs(runs_dir: Optional[Path] = None) -> list[dict]:
    root = Path(runs_dir) if runs_dir else DEFAULT_RUNS_DIR
    if not root.exists():
        return []
    out = []
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        cfg_path = run_dir / "config.json"
        if not cfg_path.exists():
            continue
        try:
            with cfg_path.open() as f:
                cfg = json.load(f)
            cfg["_path"] = str(run_dir)
            out.append(cfg)
        except Exception as e:
            logger.warning("Skipping unreadable run %s (%s)", run_dir, e)
    # newest first, by directory mtime
    out.sort(key=lambda c: c.get("_path", ""), reverse=True)
    return out
