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
    """Trigger a job by running main.py in the skuld-backend container."""
    if request.mode not in JOB_MODES:
        raise HTTPException(status_code=400, detail=f"Unknown mode: {request.mode}")

    try:
        import urllib.request
        import json as json_lib

        # Determine expected log path
        now = datetime.now()
        component = "historization" if request.mode == "historization" else "data_collector"
        date_str = now.strftime("%Y-%m-%d")
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp_str}_{component}.log"

        # Use Docker Engine API via Unix socket to exec in skuld-backend
        import http.client
        import socket

        class DockerUnixConnection(http.client.HTTPConnection):
            def __init__(self):
                super().__init__("localhost")

            def connect(self):
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect("/var/run/docker.sock")

        # Step 1: Create exec instance
        conn = DockerUnixConnection()
        exec_config = json_lib.dumps({
            "Cmd": ["/bin/bash", "/app/Skuld/run_data_collection.sh", request.mode],
            "Detach": True,
        })
        conn.request("POST", "/containers/skuld-backend/exec",
                     body=exec_config,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 201:
            error_body = resp.read().decode()
            raise HTTPException(status_code=500, detail=f"Docker exec create failed: {error_body}")
        exec_id = json_lib.loads(resp.read().decode())["Id"]

        # Step 2: Start exec
        conn2 = DockerUnixConnection()
        start_config = json_lib.dumps({"Detach": True})
        conn2.request("POST", f"/exec/{exec_id}/start",
                      body=start_config,
                      headers={"Content-Type": "application/json"})
        resp2 = conn2.getresponse()
        if resp2.status != 200:
            error_body = resp2.read().decode()
            raise HTTPException(status_code=500, detail=f"Docker exec start failed: {error_body}")
        resp2.read()  # consume response

        logger.info(f"Job triggered: {request.mode} via Docker socket exec in skuld-backend")
        return {
            "status": "triggered",
            "mode": request.mode,
            "pid": 0,
            "component": component,
            "date": date_str,
            "filename": filename,
            "started_at": now.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to trigger job {request.mode}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger: {str(e)}")


@router.get("/jobs/running")
async def get_running_jobs(current_user: dict = Depends(get_current_user)):
    """Check for active lockfiles in the skuld-backend container."""
    import http.client
    import socket
    import json as json_lib

    class DockerUnixConnection(http.client.HTTPConnection):
        def __init__(self):
            super().__init__("localhost")

        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.connect("/var/run/docker.sock")

    running = []
    try:
        # Exec a command in skuld-backend to list lockfiles and check PIDs
        conn = DockerUnixConnection()
        exec_config = json_lib.dumps({
            "Cmd": ["bash", "-c",
                    "for f in /tmp/skuld_data_collection_*.lock; do "
                    "[ -f \"$f\" ] || continue; "
                    "MODE=$(basename $f .lock | sed 's/skuld_data_collection_//'); "
                    "PID=$(cat $f); "
                    "if ps -p $PID > /dev/null 2>&1; then ALIVE=1; else ALIVE=0; fi; "
                    "START=$(stat -c %Y \"$f\" 2>/dev/null || echo 0); "
                    "echo \"$MODE:$PID:$ALIVE:$START\"; "
                    "done"],
            "AttachStdout": True,
            "AttachStderr": True,
        })
        conn.request("POST", "/containers/skuld-backend/exec",
                     body=exec_config,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 201:
            return []
        exec_id = json_lib.loads(resp.read().decode())["Id"]

        # Start exec (attached to get output)
        conn2 = DockerUnixConnection()
        start_config = json_lib.dumps({"Detach": False})
        conn2.request("POST", f"/exec/{exec_id}/start",
                      body=start_config,
                      headers={"Content-Type": "application/json"})
        resp2 = conn2.getresponse()
        if resp2.status != 200:
            return []
        raw_output = resp2.read()

        # Docker multiplexed stream: skip 8-byte frame headers
        output = ""
        i = 0
        while i < len(raw_output):
            if i + 8 <= len(raw_output):
                frame_size = int.from_bytes(raw_output[i+4:i+8], 'big')
                i += 8
                if i + frame_size <= len(raw_output):
                    output += raw_output[i:i+frame_size].decode("utf-8", errors="replace")
                i += frame_size
            else:
                break

        for line in output.strip().split("\n"):
            line = line.strip()
            if ":" in line and len(line.split(":")) >= 3:
                parts = line.split(":")
                mode = parts[0]
                pid = parts[1]
                alive = parts[2] == "1"
                started_at = None
                if len(parts) >= 4 and parts[3] != "0":
                    try:
                        started_at = datetime.fromtimestamp(int(parts[3])).isoformat()
                    except (ValueError, OSError):
                        pass
                running.append({"mode": mode, "pid": pid, "alive": alive, "started_at": started_at})
    except Exception as e:
        logger.warning(f"Could not check running jobs: {e}")

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


@router.get("/jobs/history")
async def get_job_history(
    days: int = Query(default=14, description="Number of days to look back"),
    mode_filter: str = Query(default="", description="Filter by job mode (e.g. historization)"),
    current_user: dict = Depends(get_current_user),
):
    """Parse log files to build a structured job run history.

    Reconstructs job history from filesystem logs:
    - Start time from filename (YYYYMMDD_HHMMSS_data_collector.log)
    - Status/duration from last lines of each log file
    - Error details extracted from ERROR lines
    """
    import re

    # Search across all log component directories
    log_components = ["data_collector", "historization"]
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    history = []

    for log_component in log_components:
        component_dir = LOGS_BASE / log_component
        if not component_dir.exists():
            continue

        # Iterate date directories
        try:
            date_dirs = sorted(
                [d for d in component_dir.iterdir() if d.is_dir() and d.name >= cutoff_date],
                reverse=True,
            )
        except Exception:
            continue

        for date_dir in date_dirs:
            try:
                log_files = sorted(
                    [f for f in date_dir.iterdir() if f.suffix == ".log"],
                    reverse=True,
                )
            except Exception:
                continue

            for log_file in log_files:
                try:
                    # Extract start time from filename: YYYYMMDD_HHMMSS_{component}.log
                    match = re.match(r"(\d{8}_\d{6})_(\w+)\.log", log_file.name)
                    if not match:
                        continue

                    ts_str = match.group(1)
                    started_at = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")

                    # Read last portion of the file to determine status
                    content = log_file.read_text(encoding="utf-8", errors="replace")
                    lines = content.splitlines()
                    total_lines = len(lines)

                    # Determine job mode from first few lines
                    job_mode = ""
                    for line in lines[:20]:
                        if "mode" in line.lower() or "Mode:" in line:
                            mode_match = re.search(r"[Mm]ode[:\s=]+['\"]?(\w+)", line)
                            if mode_match:
                                job_mode = mode_match.group(1)
                                break
                        # Also check for "Starting pipeline in mode: X"
                        if "Starting" in line and "pipeline" in line.lower():
                            mode_match = re.search(r"mode[:\s]+(\w+)", line, re.IGNORECASE)
                            if mode_match:
                                job_mode = mode_match.group(1)
                                break

                    # Check task lines for mode detection
                    if not job_mode:
                        for line in lines[:50]:
                            if "Starting:" in line:
                                if "historiz" in line.lower():
                                    job_mode = "historization"
                                elif "option" in line.lower():
                                    job_mode = "option_data"
                                elif "saturday" in line.lower() or "dividends" in line.lower():
                                    job_mode = "saturday_night"
                                elif "stock_data" in line.lower() or "technical_indicators" in line.lower():
                                    job_mode = "stock_data_daily"
                                elif "market_start" in line.lower() or "intraday" in line.lower():
                                    job_mode = "market_start_mid_end"
                                elif "historical_prices" in line.lower():
                                    job_mode = "historical_prices"
                                elif "historical_iv" in line.lower():
                                    job_mode = "historical_iv"
                                elif "historical_technical" in line.lower():
                                    job_mode = "historical_technical_indicators"
                                break

                    # If component is historization, default mode to historization
                    if not job_mode and log_component == "historization":
                        job_mode = "historization"

                    # Apply mode filter
                    if mode_filter and job_mode != mode_filter:
                        continue

                    # Determine status and duration from last lines
                    status = "unknown"
                    duration_seconds = None
                    error_summary = ""
                    ended_at = None

                    # Look at last 30 lines for completion indicators
                    tail_lines = lines[-30:] if len(lines) > 30 else lines
                    tail_text = "\n".join(tail_lines)

                    if "All tasks completed successfully" in tail_text or "✓" in tail_text and "success" in tail_text.lower():
                        status = "success"
                    elif "Historization Pipeline Completed Successfully" in tail_text:
                        status = "success"
                    elif "ABORTED" in tail_text or "FAILED" in tail_text or "Pipeline Failed" in tail_text:
                        status = "failed"
                    elif "with failures" in tail_text.lower() or "⚠" in tail_text:
                        status = "partial"
                    elif "timed out" in tail_text.lower():
                        status = "timeout"
                    elif "Out of Memory" in tail_text or "Exit Code 137" in tail_text:
                        status = "oom"

                    # Extract duration from report lines
                    for line in tail_lines:
                        dur_match = re.search(r"Total Runtime:\s*(\d+)s", line)
                        if dur_match:
                            duration_seconds = int(dur_match.group(1))
                            break
                        # Also match historization pipeline duration
                        dur_match2 = re.search(r"Finished in (\d+\.?\d*)s", line)
                        if dur_match2:
                            duration_seconds = int(float(dur_match2.group(1)))
                            break

                    # If no explicit duration, estimate from last timestamp
                    if duration_seconds is None and lines:
                        last_ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", lines[-1])
                        if last_ts_match:
                            try:
                                ended_at = datetime.strptime(last_ts_match.group(1), "%Y-%m-%d %H:%M:%S")
                                duration_seconds = int((ended_at - started_at).total_seconds())
                            except (ValueError, OverflowError):
                                pass

                    # Extract error lines (last 5 ERROR lines)
                    error_lines = [l for l in lines if "ERROR" in l][-5:]
                    if error_lines:
                        error_summary = "\n".join(
                            re.sub(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - \S+ - ERROR - ", "", l)
                            for l in error_lines
                        )

                    # File size as indicator of job scope
                    file_size = log_file.stat().st_size

                    history.append({
                        "date": date_dir.name,
                        "started_at": started_at.isoformat(),
                        "mode": job_mode or "unknown",
                        "status": status,
                        "duration_seconds": duration_seconds,
                        "total_lines": total_lines,
                        "file_size_kb": round(file_size / 1024, 1),
                        "error_summary": error_summary[:500],  # Truncate
                        "log_file": log_file.name,
                    })

                except Exception as e:
                    logger.debug(f"Error parsing log file {log_file}: {e}")
                    continue

    return history
