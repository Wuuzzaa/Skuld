"""Sector Rotation router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user
from api.core.database import df_to_json_safe

router = APIRouter()


@router.get("/")
async def get_sector_rotation(
    price_column: str = "adjclose",
    short_window: int = 5,
    long_window: int = 15,
    volatility_window: int = 20,
    volatility_threshold_low: float = 0.15,
    volatility_threshold_high: float = 0.30,
    lookback_days: int = 120,
    tail_days: int = 6,
    rs_weight: float = 0.60,
    momentum_weight: float = 0.40,
    mps_long_months: int = 8,
    mps_short_months: int = 6,
    allocated_capital: float = 0.0,
    current_user: dict = Depends(get_current_user),
):
    """Calculate sector rotation RS-Ratio, RS-Momentum, RRG Score, MPS, and SMA200 signals."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.sector_rotation import (
        RotationParameters,
        build_latest_sector_snapshot,
        calculate_sector_rotation,
        load_sector_rotation_price_history,
    )

    parameters = RotationParameters(
        price_column=price_column,
        short_window=short_window,
        long_window=long_window,
        volatility_window=volatility_window,
        volatility_threshold_low=volatility_threshold_low,
        volatility_threshold_high=volatility_threshold_high,
        lookback_days=lookback_days,
        tail_days=tail_days,
        rs_weight=rs_weight,
        momentum_weight=momentum_weight,
        mps_long_months=mps_long_months,
        mps_short_months=mps_short_months,
        allocated_capital=allocated_capital,
    )

    price_history = load_sector_rotation_price_history(parameters)
    rotation_data = calculate_sector_rotation(price_history, parameters)

    if rotation_data.empty:
        return {"snapshot": [], "timeseries": []}

    snapshot = build_latest_sector_snapshot(rotation_data, parameters)

    return {
        "snapshot": df_to_json_safe(snapshot),
        "timeseries": df_to_json_safe(rotation_data),
    }
