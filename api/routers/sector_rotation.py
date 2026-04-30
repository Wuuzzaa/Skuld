"""Sector Rotation router."""

from fastapi import APIRouter, Depends, Query

from api.core.auth import get_current_user

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
    current_user: dict = Depends(get_current_user),
):
    """Calculate sector rotation RS-Ratio and RS-Momentum."""
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
    )

    price_history = load_sector_rotation_price_history(parameters)
    rotation_data = calculate_sector_rotation(price_history, parameters)

    if rotation_data.empty:
        return {"snapshot": [], "timeseries": []}

    snapshot = build_latest_sector_snapshot(rotation_data)

    # Convert dates for JSON
    for col in snapshot.select_dtypes(include=["datetime64"]).columns:
        snapshot[col] = snapshot[col].astype(str)
    for col in rotation_data.select_dtypes(include=["datetime64"]).columns:
        rotation_data[col] = rotation_data[col].astype(str)

    return {
        "snapshot": snapshot.to_dict(orient="records"),
        "timeseries": rotation_data.to_dict(orient="records"),
    }
