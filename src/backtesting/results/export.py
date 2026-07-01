"""
CSV / JSON export helpers for Streamlit download-buttons.
"""

from __future__ import annotations

import io
import json
from datetime import date, datetime

import pandas as pd


def _json_default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in o.__dict__.items() if not k.startswith("_")}
    return str(o)


def export_csv(df: pd.DataFrame) -> bytes:
    if df is None or df.empty:
        return b""
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    return buffer.getvalue().encode("utf-8")


def export_json(obj) -> bytes:
    if isinstance(obj, pd.DataFrame):
        return obj.to_json(orient="records", date_format="iso").encode("utf-8")
    return json.dumps(obj, default=_json_default, indent=2).encode("utf-8")
