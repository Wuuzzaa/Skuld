"""Expected Value Monte Carlo Simulation router."""

from typing import Literal
from pydantic import BaseModel
from fastapi import APIRouter, Depends

from api.core.auth import get_current_user

router = APIRouter()


class OptionLeg(BaseModel):
    strike: float
    premium: float
    type: Literal["Call Bought", "Call Sold", "Put Bought", "Put Sold"]


class SimulationRequest(BaseModel):
    current_price: float = 170.94
    dte: int = 63
    volatility: float = 0.42
    risk_free_rate: float = 0.03
    dividend_yield: float = 0.0
    num_simulations: int = 100_000
    random_seed: int = 42
    iv_correction: str = "auto"
    transaction_cost_per_contract: float = 2.0
    options: list[OptionLeg]


@router.post("/simulate")
async def simulate_expected_value(
    request: SimulationRequest,
    current_user: dict = Depends(get_current_user),
):
    """Run Monte Carlo simulation for an options strategy."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from src.monte_carlo_simulation import UniversalOptionsMonteCarloSimulator

    options = []
    for opt in request.options:
        is_call = opt.type in ["Call Bought", "Call Sold"]
        is_long = opt.type in ["Call Bought", "Put Bought"]
        options.append({
            "strike": opt.strike,
            "premium": opt.premium,
            "is_call": is_call,
            "is_long": is_long,
        })

    simulator = UniversalOptionsMonteCarloSimulator(
        num_simulations=request.num_simulations,
        random_seed=request.random_seed,
        current_price=request.current_price,
        dte=request.dte,
        volatility=request.volatility,
        risk_free_rate=request.risk_free_rate,
        dividend_yield=request.dividend_yield,
        iv_correction=request.iv_correction,
    )

    expected_value = simulator.calculate_expected_value(options=options)

    return {
        "expected_value": round(expected_value, 2),
        "corrected_volatility": round(simulator.volatility, 6),
        "iv_correction_factor": round(simulator.iv_correction_factor, 6),
        "time_to_expiration": round(simulator.time_to_expiration, 6),
        "parameters": {
            "current_price": request.current_price,
            "dte": request.dte,
            "raw_volatility": request.volatility,
            "risk_free_rate": request.risk_free_rate,
            "num_simulations": request.num_simulations,
        },
    }
