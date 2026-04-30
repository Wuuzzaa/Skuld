"""SKULD FastAPI Backend - Main Application"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.core.database import engine
from api.routers import (
    auth,
    analyst_prices,
    spreads,
    iron_condors,
    married_puts,
    position_insurance,
    sector_rotation,
    expected_value,
    symbols,
    data_logs,
    multifactor_swingtrading,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    yield
    engine.dispose()


app = FastAPI(
    title="SKULD API",
    description="Options Trading Analysis Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(analyst_prices.router, prefix="/api/analyst-prices", tags=["Analyst Prices"])
app.include_router(spreads.router, prefix="/api/spreads", tags=["Spreads"])
app.include_router(iron_condors.router, prefix="/api/iron-condors", tags=["Iron Condors"])
app.include_router(married_puts.router, prefix="/api/married-puts", tags=["Married Puts"])
app.include_router(position_insurance.router, prefix="/api/position-insurance", tags=["Position Insurance"])
app.include_router(sector_rotation.router, prefix="/api/sector-rotation", tags=["Sector Rotation"])
app.include_router(expected_value.router, prefix="/api/expected-value", tags=["Expected Value"])
app.include_router(symbols.router, prefix="/api/symbols", tags=["Symbols"])
app.include_router(data_logs.router, prefix="/api/data-logs", tags=["Data Logs"])
app.include_router(multifactor_swingtrading.router, prefix="/api/multifactor-swingtrading", tags=["Multifactor Swingtrading"])


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}
