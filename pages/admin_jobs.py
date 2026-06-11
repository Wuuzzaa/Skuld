"""
Admin page for job management and log viewing.
Allows viewing pipeline logs, triggering jobs manually, and monitoring activity.
Uses Docker Engine API via Unix socket to exec in skuld-backend container.
"""
import logging
import http.client
import re
import socket
import json as json_lib
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd

from src.database import select_into_dataframe

logger = logging.getLogger(__name__)

# Base path for logs (shared Docker volume: ./logs:/app/Skuld/logs)
LOGS_BASE = Path(__file__).resolve().parent.parent / "logs"

# Available job modes
JOB_MODES = [
    "all",
    "saturday_night",
    "market_start_mid_end",
    "stock_data_daily",
    "option_data",
    "historical_prices",
    "historical_iv",
    "historical_volatility",
    "historical_technical_indicators",
    "historical_full",
    "historization",
    "only_run_migrations",

]

JOB_DESCRIPTIONS = {
    "all": "Full pipeline (options, stocks, analyst, earnings, fundamentals, dividends, profiles, technicals, historization)",
    "option_data": "Massive Option Chains only",
    "stock_data_daily": "Technical Indicators (daily)",
    "market_start_mid_end": "Intraday stock prices",
    "saturday_night": "Weekly data (dividends, fundamentals, analyst, earnings, profiles)",
    "historical_prices": "Backfill historical prices for all symbols",
    "historical_iv": "Backfill implied volatility history",
    "historical_technical_indicators": "Backfill technical indicators history",
    "historical_volatility": "Backfill volatility history",
    "historical_full": "Full historical backfill (prices -> technicals -> IV, sequential)",
    "historization": "Archive/version current data",
    "only_run_migrations": "Run DB migrations only (no data collection)",
}


# ==============================================================================
# Docker Engine API helpers (via Unix socket)
# ==============================================================================

class DockerUnixConnection(http.client.HTTPConnection):
    """HTTP connection over Unix socket to Docker Engine API."""
    def __init__(self):
        super().__init__("localhost")

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def _docker_exec_detached(container: str, cmd: list[str]) -> str | None:
    """Run a command detached in a container. Returns exec ID or None on failure."""
    try:
        conn = DockerUnixConnection()
        exec_config = json_lib.dumps({"Cmd": cmd, "Detach": True})
        conn.request("POST", f"/containers/{container}/exec",
                     body=exec_config,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 201:
            return None
        exec_id = json_lib.loads(resp.read().decode())["Id"]

        conn2 = DockerUnixConnection()
        start_config = json_lib.dumps({"Detach": True})
        conn2.request("POST", f"/exec/{exec_id}/start",
                      body=start_config,
                      headers={"Content-Type": "application/json"})
        resp2 = conn2.getresponse()
        resp2.read()
        return exec_id if resp2.status == 200 else None
    except Exception as e:
        logger.warning(f"Docker exec failed: {e}")
        return None


def _docker_exec_output(container: str, cmd: list[str]) -> str | None:
    """Run a command attached in a container and return stdout."""
    try:
        conn = DockerUnixConnection()
        exec_config = json_lib.dumps({
            "Cmd": cmd,
            "AttachStdout": True,
            "AttachStderr": True,
        })
        conn.request("POST", f"/containers/{container}/exec",
                     body=exec_config,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 201:
            return None
        exec_id = json_lib.loads(resp.read().decode())["Id"]

        conn2 = DockerUnixConnection()
        start_config = json_lib.dumps({"Detach": False})
        conn2.request("POST", f"/exec/{exec_id}/start",
                      body=start_config,
                      headers={"Content-Type": "application/json"})
        resp2 = conn2.getresponse()
        if resp2.status != 200:
            return None
        raw_output = resp2.read()

        # Parse Docker multiplexed stream (8-byte frame headers)
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
        return output
    except Exception as e:
        logger.warning(f"Docker exec output failed: {e}")
        return None


# ==============================================================================
# Page Layout
# ==============================================================================

st.subheader("Admin - Job Management")

tab_logs, tab_jobs, tab_history, tab_activity = st.tabs(["Log Viewer", "Trigger Jobs", "Job History", "Recent Activity"])

# ==============================================================================
# TAB 1: LOG VIEWER
# ==============================================================================
with tab_logs:
    st.markdown("#### Pipeline Logs")

    # Discover available components from local shared volume
    components = []
    if LOGS_BASE.exists():
        components = sorted([d.name for d in LOGS_BASE.iterdir() if d.is_dir()])

    if not components:
        st.info("No log directories found. Logs appear after jobs run.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            selected_component = st.selectbox("Component", components, index=0)
        with col2:
            component_dir = LOGS_BASE / selected_component
            dates = sorted(
                [d.name for d in component_dir.iterdir() if d.is_dir()],
                reverse=True
            ) if component_dir.exists() else []

            if dates:
                selected_date = st.selectbox("Date", dates, index=0)
            else:
                selected_date = None
                st.warning("No log dates available for this component.")

        if selected_date:
            log_dir = component_dir / selected_date
            log_files = sorted(
                [f for f in log_dir.iterdir() if f.suffix == ".log"],
                key=lambda f: f.name,
                reverse=True
            )

            if log_files:
                selected_file = st.selectbox(
                    "Log File",
                    log_files,
                    format_func=lambda f: f.name,
                    index=0
                )

                # Filter options
                col_filter1, col_filter2 = st.columns(2)
                with col_filter1:
                    log_level_filter = st.multiselect(
                        "Filter by Level",
                        ["ERROR", "WARNING", "INFO", "DEBUG"],
                        default=["ERROR", "WARNING", "INFO"]
                    )
                with col_filter2:
                    search_term = st.text_input("Search in logs", placeholder="e.g. timeout, OOM, failed")

                # Read and display log
                if selected_file:
                    try:
                        content = selected_file.read_text(encoding="utf-8", errors="replace")
                        lines = content.splitlines()

                        # Apply filters
                        if log_level_filter:
                            filtered = []
                            for line in lines:
                                for level in log_level_filter:
                                    if level in line:
                                        filtered.append(line)
                                        break
                            lines = filtered

                        if search_term:
                            lines = [l for l in lines if search_term.lower() in l.lower()]

                        st.caption(f"{len(lines)} lines displayed | File: {selected_file.name}")

                        max_lines = st.slider("Lines to show", 50, 2000, 500, step=50)
                        display_lines = lines[-max_lines:] if len(lines) > max_lines else lines

                        log_text = "\n".join(display_lines)
                        st.code(log_text, language="log")

                    except Exception as e:
                        st.error(f"Error reading log file: {e}")
            else:
                st.info("No log files for this date.")

    # Cron schedule reference
    st.markdown("---")
    st.markdown("#### Cron Schedule Reference")
    with st.expander("Show Cron Schedule"):
        st.code("""# Option Data: Monday-Friday, every 30 min 08:00-21:00 UTC
0,30 8-20 * * 1-5  option_data

# Saturday Night: Saturday 21:00 UTC
0 21 * * 6  saturday_night

# Market Start/Mid/End: M-F at 09:15, 14:15, 19:15 UTC
15 9,14,19 * * 1-5  market_start_mid_end

# Stock Data Daily: M-F 09:45 UTC
45 9 * * 1-5  stock_data_daily

# Historization: M-F 21:30 UTC
30 21 * * 1-5  historization""", language="bash")


# ==============================================================================
# TAB 2: TRIGGER JOBS (with Live Log)
# ==============================================================================
with tab_jobs:
    st.markdown("#### Manually Trigger Jobs")
    st.info(
        "Jobs run inside the **skuld-backend** Docker container. "
        "Triggering from here uses the Docker Engine API via mounted socket."
    )

    selected_mode = st.selectbox(
        "Job Mode",
        JOB_MODES,
        format_func=lambda m: f"{m} - {JOB_DESCRIPTIONS.get(m, '')}",
    )

    st.info(f"**{selected_mode}**: {JOB_DESCRIPTIONS.get(selected_mode, 'No description')}")

    # Initialize live log session state
    if "live_log_active" not in st.session_state:
        st.session_state.live_log_active = False
        st.session_state.live_log_component = ""
        st.session_state.live_log_date = ""
        st.session_state.live_log_filename = ""
        st.session_state.live_log_mode = ""
        st.session_state.live_log_since_line = 0
        st.session_state.live_log_retry_count = 0

    # Trigger button
    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        trigger = st.button("Start Job", type="primary", use_container_width=True)

    if trigger:
        with col_status:
            with st.spinner(f"Triggering {selected_mode}..."):
                cmd = ["/bin/bash", "/app/Skuld/run_data_collection.sh", selected_mode]
                exec_id = _docker_exec_detached("skuld-backend", cmd)

                if exec_id:
                    now = datetime.now()
                    st.success(f"Job **{selected_mode}** triggered successfully!")
                    # Set up live log tracking
                    st.session_state.live_log_active = True
                    st.session_state.live_log_component = "data_collector"
                    st.session_state.live_log_date = now.strftime("%Y-%m-%d")
                    st.session_state.live_log_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_data_collector.log"
                    st.session_state.live_log_mode = selected_mode
                    st.session_state.live_log_since_line = 0
                    st.session_state.live_log_retry_count = 0
                else:
                    st.error(
                        "Failed to trigger job. Possible causes:\n"
                        "- Docker socket not mounted (`/var/run/docker.sock`)\n"
                        "- `skuld-backend` container not running"
                    )

    # Live Log Panel
    if st.session_state.live_log_active:
        st.markdown("---")
        st.markdown(f"#### Live Log Output — `{st.session_state.live_log_mode}`")

        log_file_path = (
            LOGS_BASE
            / st.session_state.live_log_component
            / st.session_state.live_log_date
            / st.session_state.live_log_filename
        )

        col_refresh, col_stop = st.columns([1, 1])
        with col_refresh:
            refresh_log = st.button("Refresh Log", type="secondary", use_container_width=True)
        with col_stop:
            if st.button("Stop Live View", use_container_width=True):
                st.session_state.live_log_active = False
                st.rerun()

        if log_file_path.exists():
            try:
                content = log_file_path.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                total_lines = len(lines)
                st.session_state.live_log_since_line = total_lines
                st.session_state.live_log_retry_count = 0

                st.caption(f"Total: {total_lines} lines | File: {st.session_state.live_log_filename}")

                # Show last 200 lines
                display_lines = lines[-200:] if len(lines) > 200 else lines
                log_text = "\n".join(display_lines)
                st.code(log_text, language="log")
            except Exception as e:
                st.warning(f"Error reading log: {e}")
        else:
            # Fallback: try to find the actual latest log file
            st.session_state.live_log_retry_count += 1
            if st.session_state.live_log_retry_count >= 3:
                component_dir = LOGS_BASE / st.session_state.live_log_component
                if component_dir.exists():
                    date_dirs = sorted([d for d in component_dir.iterdir() if d.is_dir()], reverse=True)
                    if date_dirs:
                        latest_date = date_dirs[0]
                        files = sorted(
                            [f for f in latest_date.iterdir() if f.suffix == ".log"],
                            key=lambda f: f.name,
                            reverse=True,
                        )
                        if files:
                            st.session_state.live_log_date = latest_date.name
                            st.session_state.live_log_filename = files[0].name
                            st.session_state.live_log_retry_count = 0
                            st.rerun()

            st.info(f"Waiting for log file to appear: `{st.session_state.live_log_filename}`")
            st.caption("The log file will be created once the job starts writing output. Click Refresh.")

        if refresh_log:
            st.rerun()

    # Running Jobs section
    st.markdown("---")
    st.markdown("#### Running Jobs")
    st.caption("Checks for active lockfiles in the backend container.")

    if st.button("Check Running Jobs"):
        output = _docker_exec_output("skuld-backend", [
            "bash", "-c",
            "for f in /tmp/skuld_data_collection_*.lock; do "
            "[ -f \"$f\" ] || continue; "
            "MODE=$(basename $f .lock | sed 's/skuld_data_collection_//'); "
            "PID=$(cat $f); "
            "if ps -p $PID > /dev/null 2>&1; then ALIVE=1; else ALIVE=0; fi; "
            "echo \"$MODE:$PID:$ALIVE\"; "
            "done"
        ])

        if output is None:
            st.warning("Could not reach Docker socket. Is `/var/run/docker.sock` mounted?")
        elif output.strip():
            for line in output.strip().split("\n"):
                line = line.strip()
                if ":" in line and len(line.split(":")) >= 3:
                    parts = line.split(":")
                    mode, pid, alive = parts[0], parts[1], parts[2] == "1"
                    icon = "🟢" if alive else "🔴"
                    status_text = "running" if alive else "stale lockfile"
                    st.write(f"{icon} **{mode}** — PID {pid} ({status_text})")
        else:
            st.success("No jobs currently running.")


# ==============================================================================
# TAB 3: JOB HISTORY (parsed from log files)
# ==============================================================================
with tab_history:
    st.markdown("#### Job Run History")
    st.caption("Parsed from log files — shows status, duration, and errors for past job runs.")

    col_days, col_mode = st.columns(2)
    with col_days:
        history_days = st.selectbox("Time Range", [3, 7, 14, 30], index=2,
                                    format_func=lambda d: f"Last {d} days")
    with col_mode:
        history_mode_filter = st.selectbox("Filter by Mode", ["All"] + JOB_MODES,
                                           key="history_mode_filter")

    # Parse log files locally (same shared Docker volume as Log Viewer)
    cutoff_date = (datetime.now() - timedelta(days=history_days)).strftime("%Y-%m-%d")
    history_entries = []

    # Scan all component directories (dynamic, same as Log Viewer)
    if LOGS_BASE.exists():
        log_components = [d.name for d in LOGS_BASE.iterdir() if d.is_dir()]
    else:
        log_components = []

    for component in log_components:
        comp_dir = LOGS_BASE / component
        if not comp_dir.exists():
            continue
        for date_dir in comp_dir.iterdir():
            if not date_dir.is_dir() or date_dir.name < cutoff_date:
                continue
            for log_file in date_dir.iterdir():
                if log_file.suffix != ".log":
                    continue
                # Extract start time from filename: YYYYMMDD_HHMMSS_component.log
                match = re.match(r"(\d{8})_(\d{6})_", log_file.name)
                if not match:
                    continue

                started_str = match.group(2)
                started_time = f"{started_str[:2]}:{started_str[2:4]}"

                # Detect mode from first 50 lines
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        head_lines = [f.readline() for _ in range(50)]
                    tail_text = log_file.read_text(encoding="utf-8", errors="replace")
                    all_lines = tail_text.splitlines()
                    tail_lines = all_lines[-30:] if len(all_lines) > 30 else all_lines
                    tail_joined = "\n".join(tail_lines)
                except Exception:
                    continue

                # Mode detection
                mode = "unknown"
                for line in head_lines:
                    if not line:
                        continue
                    # Pattern: "Starting: option_data" or "mode: all"
                    m = re.search(r"(?:Starting|mode)[:\s]+(\w+)", line, re.IGNORECASE)
                    if m and m.group(1).lower() in [x.lower() for x in JOB_MODES]:
                        mode = m.group(1).lower()
                        break
                if mode == "unknown":
                    mode = component  # fallback to component name

                # Apply mode filter
                if history_mode_filter != "All" and mode != history_mode_filter:
                    continue

                # Status detection from tail (aligned with pipeline_monitor.py output)
                status = "unknown"
                if re.search(r"✗.*ABORTED|Pipeline ABORTED", tail_joined):
                    status = "failed"
                elif re.search(r"Out of Memory|Exit Code 137", tail_joined, re.IGNORECASE):
                    status = "oom"
                elif re.search(r"timed out", tail_joined, re.IGNORECASE):
                    status = "timeout"
                elif re.search(r"⚠.*finished with.*failure", tail_joined):
                    status = "partial"
                elif re.search(r"✓.*All tasks completed successfully", tail_joined):
                    status = "success"
                elif re.search(r"Historization Pipeline Completed Successfully", tail_joined):
                    status = "success"

                # Duration extraction
                duration_seconds = None
                dur_match = re.search(r"Total Runtime:\s*(\d+)s", tail_joined)
                if dur_match:
                    duration_seconds = int(dur_match.group(1))
                else:
                    dur_match2 = re.search(r"Finished in\s+([\d.]+)s", tail_joined)
                    if dur_match2:
                        duration_seconds = int(float(dur_match2.group(1)))

                # Error summary (last ERROR lines)
                error_lines = [l for l in all_lines if "ERROR" in l]
                error_summary = "\n".join(error_lines[-5:]) if error_lines else ""

                # File stats
                file_size_kb = log_file.stat().st_size / 1024
                total_lines = len(all_lines)

                history_entries.append({
                    "date": date_dir.name,
                    "started": started_time,
                    "mode": mode,
                    "status": status,
                    "duration_seconds": duration_seconds,
                    "total_lines": total_lines,
                    "file_size_kb": file_size_kb,
                    "error_summary": error_summary,
                    "log_path": str(log_file),
                })

    # Sort by date + started descending
    history_entries.sort(key=lambda x: (x["date"], x["started"]), reverse=True)

    if history_entries:
        # Statistics cards
        total = len(history_entries)
        successful = sum(1 for j in history_entries if j["status"] == "success")
        failed = sum(1 for j in history_entries if j["status"] in ("failed", "timeout", "oom"))

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric("Total Runs", total)
        with col_s2:
            st.metric("Successful", successful)
        with col_s3:
            st.metric("Failed", failed)

        # Format duration
        def _fmt_duration(seconds):
            if not seconds:
                return "—"
            s = int(seconds)
            if s >= 3600:
                return f"{s // 3600}h {(s % 3600) // 60}m"
            elif s >= 60:
                return f"{s // 60}m {s % 60}s"
            return f"{s}s"

        STATUS_LABELS = {
            "success": "OK",
            "failed": "FAILED",
            "partial": "PARTIAL",
            "timeout": "TIMEOUT",
            "oom": "OOM",
            "unknown": "?",
        }

        # Build display dataframe
        rows = []
        for job in history_entries:
            rows.append({
                "Date": job["date"],
                "Started": job["started"],
                "Mode": job["mode"],
                "Status": STATUS_LABELS.get(job["status"], "?"),
                "Duration": _fmt_duration(job["duration_seconds"]),
                "Lines": f"{job['total_lines']:,}",
                "Size": f"{job['file_size_kb']:.0f} KB",
            })

        df_history = pd.DataFrame(rows)

        def _color_status(val):
            colors = {
                "OK": "background-color: #d4edda; color: #155724;",
                "FAILED": "background-color: #f8d7da; color: #721c24;",
                "PARTIAL": "background-color: #fff3cd; color: #856404;",
                "TIMEOUT": "background-color: #ffe0b2; color: #e65100;",
                "OOM": "background-color: #f8d7da; color: #721c24;",
                "?": "background-color: #e2e3e5; color: #383d41;",
            }
            return colors.get(val, "")

        styled_df = df_history.style.map(_color_status, subset=["Status"])
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        # Expandable log detail per job
        st.markdown("---")
        st.markdown("#### Job Details")
        st.caption("Click a job to view its full log output.")
        for idx, job in enumerate(history_entries[:50]):  # limit to avoid UI overload
            status_label = STATUS_LABELS.get(job["status"], "?")
            label = f"{job['date']} {job['started']} — {job['mode']} ({status_label})"
            if job["error_summary"]:
                label += " ⚠"
            with st.expander(label):
                if job["error_summary"]:
                    st.error("**Errors found:**")
                    st.code(job["error_summary"][:1500], language="log")
                    st.markdown("---")
                # Full log content
                log_path = Path(job["log_path"])
                if log_path.exists():
                    try:
                        content = log_path.read_text(encoding="utf-8", errors="replace")
                        lines = content.splitlines()
                        st.caption(f"{len(lines)} lines | {job.get('file_size_kb', 0):.0f} KB")
                        # Lines to show: default "All" so the user actually sees the
                        # full log. Using a selectbox (not slider) avoids dragging
                        # through intermediate values, each of which triggers a
                        # Streamlit rerun and collapses this expander.
                        line_options = ["All", 500, 1000, 2000, 5000, 10000]
                        max_show = st.selectbox(
                            "Lines to display",
                            line_options,
                            index=0,
                            key=f"hist_lines_{idx}",
                        )
                        if max_show == "All" or len(lines) <= max_show:
                            display = lines
                        else:
                            display = lines[-max_show:]
                        st.code("\n".join(display), language="log")
                    except Exception as e:
                        st.warning(f"Error reading log: {e}")
                else:
                    st.info("Log file no longer available on disk.")
    else:
        st.info(f"No job runs found in the last {history_days} days.")


# ==============================================================================
# TAB 4: RECENT ACTIVITY (from DataChangeLogs)
# ==============================================================================
with tab_activity:
    st.markdown("#### Recent Data Operations")

    hours_back = st.selectbox("Show last", [6, 12, 24, 48, 72, 168], index=2,
                              format_func=lambda h: f"{h} hours" if h < 48 else f"{h // 24} days")

    try:
        cutoff = (datetime.now() - timedelta(hours=hours_back)).strftime("%Y-%m-%d %H:%M:%S")
        df = select_into_dataframe(
            f"""SELECT * FROM "DataChangeLogs"
                WHERE timestamp >= '{cutoff}'
                ORDER BY timestamp DESC"""
        )

        if not df.empty:
            # Summary metrics
            col_m1, col_m2, col_m3 = st.columns(3)
            with col_m1:
                st.metric("Total Operations", len(df))
            with col_m2:
                total_rows = df["affected_rows"].sum() if "affected_rows" in df.columns else 0
                st.metric("Rows Affected", f"{int(total_rows):,}")
            with col_m3:
                tables_touched = df["table_name"].nunique() if "table_name" in df.columns else 0
                st.metric("Tables Touched", tables_touched)

            # Filter by table
            if "table_name" in df.columns:
                tables = ["All"] + sorted(df["table_name"].unique().tolist())
                selected_table = st.selectbox("Filter by Table", tables)
                if selected_table != "All":
                    df = df[df["table_name"] == selected_table]

            st.dataframe(df, use_container_width=True)
        else:
            st.info(f"No data operations in the last {hours_back} hours.")
    except Exception as e:
        st.error(f"Error loading activity data: {e}")
