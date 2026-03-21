import numpy as np
import pandas as pd

from src.sector_rotation import (
    RotationParameters,
    build_latest_sector_snapshot,
    calculate_sector_rotation,
    classify_quadrant,
    classify_volatility_signal,
    required_history_length,
    weighted_moving_average,
)


def test_weighted_moving_average_uses_linear_weights():
    values = np.array([1.0, 2.0, 3.0])
    assert weighted_moving_average(values) == 14 / 6


def test_volatility_signal_thresholds_are_applied():
    assert classify_volatility_signal(0.10, 0.15, 0.30) == "Gruen"
    assert classify_volatility_signal(0.20, 0.15, 0.30) == "Orange"
    assert classify_volatility_signal(0.40, 0.15, 0.30) == "Rot"


def test_quadrant_classification_matches_rrg_logic():
    assert classify_quadrant(101, 101) == "Leading"
    assert classify_quadrant(101, 99) == "Weakening"
    assert classify_quadrant(99, 99) == "Lagging"
    assert classify_quadrant(99, 101) == "Improving"


def test_required_history_length_supports_short_history_setup():
    parameters = RotationParameters(short_window=5, long_window=15)
    assert required_history_length(parameters) == 28


def test_calculate_sector_rotation_returns_latest_snapshot_with_expected_columns():
    dates = pd.date_range("2024-01-01", periods=90, freq="B")
    benchmark = 100 + np.arange(len(dates)) * 0.2
    technology = 100 + np.arange(len(dates)) * 0.35
    finance = 100 + np.sin(np.arange(len(dates)) / 5) + np.arange(len(dates)) * 0.12

    data = pd.concat(
        [
            pd.DataFrame({"date": dates, "symbol": "SPY", "adjclose": benchmark, "close": benchmark}),
            pd.DataFrame({"date": dates, "symbol": "XLK", "adjclose": technology, "close": technology}),
            pd.DataFrame({"date": dates, "symbol": "XLF", "adjclose": finance, "close": finance}),
        ],
        ignore_index=True,
    )

    parameters = RotationParameters(lookback_days=120, tail_days=5)
    rotation = calculate_sector_rotation(data, parameters)

    assert not rotation.empty
    assert {"rs_ratio", "rs_momentum", "historical_volatility", "quadrant"}.issubset(rotation.columns)

    latest = build_latest_sector_snapshot(rotation)
    assert set(latest["symbol"]) == {"XLK", "XLF"}
    assert latest["volatility_pct"].notna().all()