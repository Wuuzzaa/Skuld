"""Admin router for job management and log viewing."""

import subprocess
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.core.auth import get_current_user
from api.core.database import query_dataframe, df_to_json_safe

logger = logging.getLogger(__name__)

router = APIRouter()

# Base path for logs inside Docker container
LOGS_BASE = Path("/app/Skuld/logs")

JOB_MODES = [
    "all",
    "option_data",
    "stock_data_daily",
    "market_start_mid_end",
    "saturday_night",
    "historical_prices",
    "historical_iv",
    "historical_technical_indicators",
    "historical_full",
    "historization",
    "only_run_migrations",
]


class TriggerJobRequest(BaseModel):
    mode: str


@router.get("/logs/components")
async def get_log_components(current_user: dict = Depends(get_current_user)):
    """List available log components (subdirectories)."""
    if not LOGS_BASE.exists():
        return []
    return sorted([d.name for d in LOGS_BASE.iterdir() if d.is_dir()])


@router.get("/logs/dates/{component}")
async def get_log_dates(component: str, current_user: dict = Depends(get_current_user)):
    """List available dates for a component."""
    component_dir = LOGS_BASE / component
    if not component_dir.exists():
        return []
    return sorted([d.name for d in component_dir.iterdir() if d.is_dir()], reverse=True)


@router.get("/logs/files/{component}/{date}")
async def get_log_files(component: str, date: str, current_user: dict = Depends(get_current_user)):
    """List log files for a component/date."""
    log_dir = LOGS_BASE / component / date
    if not log_dir.exists():
        return []
    files = sorted(
        [f.name for f in log_dir.iterdir() if f.suffix == ".log"],
        reverse=True
    )
    return files


@router.get("/logs/content/{component}/{date}/{filename}")
async def get_log_content(
    component: str,
    date: str,
    filename: str,
    level: str = Query(default="", description="Comma-separated levels: ERROR,WARNING,INFO,DEBUG"),
    search: str = Query(default="", description="Search term"),
    tail: int = Query(default=500, description="Number of lines from end"),
    current_user: dict = Depends(get_current_user),
):
    """Read log file content with optional filtering."""
    log_file = LOGS_BASE / component / date / filename
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        # Filter by level
        if level:
            levels = [l.strip().upper() for l in level.split(",")]
            lines = [line for line in lines if any(lv in line for lv in levels)]

        # Filter by search term
        if search:
            lines = [line for line in lines if search.lower() in line.lower()]

        total_lines = len(lines)
        # Return tail
        lines = lines[-tail:]

        return {
            "total_lines": total_lines,
            "displayed_lines": len(lines),
            "content": lines,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")


@router.get("/jobs/modes")
async def get_job_modes(current_user: dict = Depends(get_current_user)):
    """List available job modes."""
    descriptions = {
        "all": "Full pipeline (options, stocks, analyst, earnings, fundamentals, dividends, profiles, technicals, historization)",
        "option_data": "Massive Option Chains only",
        "stock_data_daily": "Technical Indicators (daily)",
        "market_start_mid_end": "Intraday stock prices",
        "saturday_night": "Weekly data (dividends, fundamentals, analyst, earnings, profiles)",
        "historical_prices": "Backfill historical prices for all symbols",
        "historical_iv": "Backfill implied volatility history",
        "historical_technical_indicators": "Backfill technical indicators history",
        "historical_full": "Full historical backfill (prices -> technicals -> IV, sequential)",
        "historization": "Archive/version current data",
        "only_run_migrations": "Run DB migrations only (no data collection)",
    }
    return [{"mode": m, "description": descriptions.get(m, "")} for m in JOB_MODES]


@router.post("/jobs/trigger")
async def trigger_job(request: TriggerJobRequest, current_user: dict = Depends(get_current_user)):
    """Trigger a job by running main.py in the background."""
    if request.mode not in JOB_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {request.mode}")

    try:
        # Determine expected log path
        now = datetime.now()
        component = "data_collector"
        date_str = now.strftime("%Y-%m-%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{component}.log"

        # Run in background using subprocess (detached)
        cmd = ["/bin/bash", "/app/Skuld/run_data_collection.sh", request.mode]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"Job triggered: {request.mode} (PID: {process.pid})")
        return {
            "status": "triggered",
            "mode": request.mode,
            "pid": process.pid,
            "component": component,
            "date": date_str,
            "filename": filename,
            "started_at": now.isoformat(),
        }
    except Exception as e:
        logger.error(f"Failed to trigger job {request.mode}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger: {str(e)}")


@router.get("/jobs/running")
async def get_running_jobs(current_user: dict = Depends(get_current_user)):
    """Check for active lockfiles to determine running jobs."""
    import glob

    lockfiles = glob.glob("/tmp/skuld_data_collection_*.lock")
    running = []
    for lf in lockfiles:
        mode = Path(lf).stem.replace("skuld_data_collection_", "")
        try:
            pid = Path(lf).read_text().strip()
            # Check if PID is still alive
            result = subprocess.run(["ps", "-p", pid], capture_output=True)
            is_alive = result.returncode == 0
            running.append({"mode": mode, "pid": pid, "alive": is_alive})
        except Exception:
            running.append({"mode": mode, "pid": "?", "alive": False})

    return running


@router.get("/activity")
async def get_recent_activity(
    hours: int = Query(default=24, description="Hours to look back"),
    table: str = Query(default="", description="Filter by table name"),
    current_user: dict = Depends(get_current_user),
):
    """Get recent data operations from DataChangeLogs."""
    cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

    sql = f"""SELECT * FROM "DataChangeLogs"
              WHERE timestamp >= '{cutoff}'"""
    if table:
        sql += f""" AND table_name = '{table}'"""
    sql += " ORDER BY timestamp DESC LIMIT 1000"

    df = query_dataframe(sql)
    return df_to_json_safe(df)


@router.get("/activity/tables")
async def get_activity_tables(current_user: dict = Depends(get_current_user)):
    """Get distinct table names from DataChangeLogs."""
    df = query_dataframe('SELECT DISTINCT table_name FROM "DataChangeLogs" ORDER BY table_name')
    return df["table_name"].tolist()


@router.get("/schedule")
async def get_cron_schedule(current_user: dict = Depends(get_current_user)):
    """Return the cron schedule reference."""
    return [
        {"schedule": "0,30 8-20 * * 1-5", "mode": "option_data", "description": "Every 30 min, Mon-Fri 08:00-21:00 UTC"},
        {"schedule": "0 21 * * 6", "mode": "saturday_night", "description": "Saturday 21:00 UTC"},
        {"schedule": "15 9,14,19 * * 1-5", "mode": "market_start_mid_end", "description": "Mon-Fri 09:15, 14:15, 19:15 UTC"},
        {"schedule": "45 9 * * 1-5", "mode": "stock_data_daily", "description": "Mon-Fri 09:45 UTC"},
        {"schedule": "30 21 * * 1-5", "mode": "historization", "description": "Mon-Fri 21:30 UTC"},
    ]


@router.get("/logs/tail/{component}/{date}/{filename}")
async def tail_log(
    component: str,
    date: str,
    filename: str,
    since_line: int = Query(default=0, description="Return lines starting from this line number"),
    limit: int = Query(default=200, description="Max lines to return"),
    current_user: dict = Depends(get_current_user),
):
    """Read new log lines since a given line number. Used for live tailing."""
    log_file = LOGS_BASE / component / date / filename
    if not log_file.exists():
        return {"total_lines": 0, "lines": [], "has_more": False}

    try:
        content = log_file.read_text(encoding="utf-8", errors="replace")
        all_lines = content.splitlines()
        total_lines = len(all_lines)

        start_idx = max(0, since_line)
        returned_lines = all_lines[start_idx:start_idx + limit]

        return {
            "total_lines": total_lines,
            "lines": returned_lines,
            "has_more": total_lines > start_idx + limit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log: {str(e)}")


@router.get("/logs/latest/{component}")
async def get_latest_log(component: str, current_user: dict = Depends(get_current_user)):
    """Find the most recent log file for a component."""
    component_dir = LOGS_BASE / component
    if not component_dir.exists():
        return None

    # Get latest date directory
    dates = sorted([d for d in component_dir.iterdir() if d.is_dir()], reverse=True)
    if not dates:
        return None

    # Get latest file in that date
    latest_date = dates[0]
    files = sorted(
        [f for f in latest_date.iterdir() if f.suffix == ".log"],
        key=lambda f: f.name,
        reverse=True,
    )
    if not files:
        return None

    return {
        "component": component,
        "date": latest_date.name,
        "filename": files[0].name,
    }
