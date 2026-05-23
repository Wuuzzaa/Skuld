"""SKULD FastAPI Backend - Main Application"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.core.config import settings
from api.core.database import engine
from api.core import cache
from api.routers import (
    admin,
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
    rsl_momentum,
    universe,
    watchlist,
    covered_calls,
    correlation,
    dividend_screener,
    dividend_portfolio_builder,
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
app.include_router(rsl_momentum.router, prefix="/api/rsl-momentum", tags=["RSL Momentum"])
app.include_router(universe.router, prefix="/api/universe", tags=["Universe"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["Watchlist"])
app.include_router(covered_calls.router, prefix="/api/covered-calls", tags=["Covered Calls"])
app.include_router(correlation.router, prefix="/api/correlation", tags=["Correlation"])
app.include_router(dividend_screener.router, prefix="/api/dividend-screener", tags=["Dividend Screener"])
app.include_router(dividend_portfolio_builder.router, prefix="/api/dividend-portfolio", tags=["Dividend Portfolio Builder"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])


@app.get("/api/health")
@app.get("/health")
async def health_check():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/api/health/db")
async def db_health_check():
    """Check database connectivity and basic data availability."""
    from sqlalchemy import text as sql_text
    try:
        with engine.connect() as conn:
            result = conn.execute(sql_text('SELECT count(*) FROM "StockData"'))
            stock_count = result.scalar()
            result = conn.execute(sql_text('SELECT count(*) FROM "OptionData" WHERE days_to_expiration > 0'))
            option_count = result.scalar()
        return {
            "status": "ok",
            "database": "connected",
            "stock_data_count": stock_count,
            "option_data_count": option_count,
        }
    except Exception as e:
        return {"status": "error", "database": "disconnected", "error": str(e)}


@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all API caches. Useful after data refresh."""
    cache.invalidate()
    return {"status": "cleared"}
