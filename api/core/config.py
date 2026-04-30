"""Core configuration for SKULD API."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings:
    # App
    APP_VERSION: str = os.getenv("SKULD_VERSION", "dev")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "admin")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "Skuld")

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://test.skuld-options.com",
        "https://app.skuld-options.com",
    ]

    # Paths
    SQL_QUERY_DIR: Path = BASE_DIR / "db" / "SQL" / "query"
    SYMBOLS_FILE: Path = BASE_DIR / "symbols_exchange.xlsx"

    # Trading
    RISK_FREE_RATE: float = 0.03
    NUM_SIMULATIONS: int = 100_000
    TRANSACTION_COST_PER_CONTRACT: float = 2.0


settings = Settings()
