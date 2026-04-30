"""Database connection for FastAPI - reuses existing SKULD DB layer."""

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool

from api.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)


def query_dataframe(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Execute SQL and return a pandas DataFrame."""
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


def query_sql_file(filename: str, params: dict | None = None) -> pd.DataFrame:
    """Execute a SQL file from the query directory and return DataFrame."""
    sql_path = settings.SQL_QUERY_DIR / filename
    sql = sql_path.read_text(encoding="utf-8")
    return query_dataframe(sql, params)


def execute_sql(sql: str, params: dict | None = None):
    """Execute SQL without returning results."""
    with engine.connect() as conn:
        conn.execute(text(sql), params or {})
        conn.commit()


def df_to_json_safe(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to JSON-safe list of dicts (handles NaN/Inf/timestamps)."""
    df = df.replace([np.inf, -np.inf], np.nan)
    for col in df.select_dtypes(include=["datetime64"]).columns:
        df[col] = df[col].astype(str)
    return df.where(df.notna(), None).to_dict(orient="records")
