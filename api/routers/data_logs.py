"""Data Change Logs router."""

from fastapi import APIRouter, Depends

from api.core.auth import get_current_user
from api.core.database import query_dataframe, df_to_json_safe

router = APIRouter()


@router.get("/")
async def get_data_logs(current_user: dict = Depends(get_current_user)):
    """Get data change logs."""
    df = query_dataframe('SELECT * FROM "DataChangeLogs" ORDER BY timestamp DESC LIMIT 500')
    return df_to_json_safe(df)
