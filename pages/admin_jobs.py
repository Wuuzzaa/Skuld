"""
Admin page for job management and log viewing.
Allows viewing pipeline logs and triggering jobs manually.
"""
import logging
import subprocess
import os
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd

from src.database import select_into_dataframe

logger = logging.getLogger(__name__)

# Base path for logs (works both locally and in Docker)
LOGS_BASE = Path(__file__).resolve().parent.parent / "logs"

# Available job modes (from main.py argument parser)
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

JOB_DESCRIPTIONS = {
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


st.subheader("Admin - Job Management")

tab_logs, tab_jobs, tab_activity = st.tabs(["Log Viewer", "Trigger Jobs", "Recent Activity"])

# ==============================================================================
# TAB 1: LOG VIEWER
# ==============================================================================
with tab_logs:
    st.markdown("#### Pipeline Logs")

    # Discover available components
    components = []
    if LOGS_BASE.exists():
        components = sorted([d.name for d in LOGS_BASE.iterdir() if d.is_dir()])

    if not components:
        st.info("No log directories found. Logs appear after jobs run in Docker.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            selected_component = st.selectbox("Component", components, index=0)
        with col2:
            # Discover available dates for this component
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

                        # Stats
                        st.caption(f"{len(lines)} lines displayed | File: {selected_file.name}")

                        # Show last N lines (most recent first)
                        max_lines = st.slider("Lines to show", 50, 2000, 500, step=50)
                        display_lines = lines[-max_lines:] if len(lines) > max_lines else lines

                        # Color-code log output
                        log_text = "\n".join(display_lines)
                        st.code(log_text, language="log")

                    except Exception as e:
                        st.error(f"Error reading log file: {e}")
            else:
                st.info("No log files for this date.")

    # Cron logs (from /var/log/ in Docker)
    st.markdown("---")
    st.markdown("#### Cron Logs (Backend Container)")
    st.caption("These logs are available inside the skuld-backend container at /var/log/cron_*.log")

    # Show cron schedule for reference
    with st.expander("Cron Schedule Reference"):
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
    st.warning(
        "Jobs run inside the **skuld-backend** Docker container. "
        "Triggering from here executes `docker exec` on the host. "
        "Make sure the container is running."
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

    # Safety: confirm before triggering
    col_btn, col_status = st.columns([1, 3])
    with col_btn:
        trigger = st.button("Start Job", type="primary", use_container_width=True)

    if trigger:
        with col_status:
            with st.spinner(f"Triggering {selected_mode}..."):
                try:
                    # Execute via docker exec on the backend container
                    cmd = [
                        "docker", "exec", "-d", "skuld-backend",
                        "/bin/bash", "/app/Skuld/run_data_collection.sh", selected_mode
                    ]
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        st.success(
                            f"Job **{selected_mode}** triggered successfully!"
                        )
                        # Set up live log tracking
                        now = datetime.now()
                        st.session_state.live_log_active = True
                        st.session_state.live_log_component = "data_collector"
                        st.session_state.live_log_date = now.strftime("%Y-%m-%d")
                        st.session_state.live_log_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_data_collector.log"
                        st.session_state.live_log_mode = selected_mode
                        st.session_state.live_log_since_line = 0
                    else:
                        st.error(f"Failed to trigger job: {result.stderr or result.stdout}")
                except subprocess.TimeoutExpired:
                    st.error("Timeout: Could not reach Docker. Is the backend container running?")
                except FileNotFoundError:
                    st.error("Docker CLI not found. This feature works on the server where Docker is running.")
                except Exception as e:
                    st.error(f"Error: {e}")

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

                # Show new lines since last check
                new_lines = lines[st.session_state.live_log_since_line:]
                st.session_state.live_log_since_line = total_lines

                st.caption(f"Total: {total_lines} lines | File: {st.session_state.live_log_filename}")

                # Show last 200 lines of the full log (most recent)
                display_lines = lines[-200:] if len(lines) > 200 else lines
                log_text = "\n".join(display_lines)
                st.code(log_text, language="log")
            except Exception as e:
                st.warning(f"Error reading log: {e}")
        else:
            st.info(f"Waiting for log file to appear: `{st.session_state.live_log_filename}`")
            st.caption("The log file will be created once the job starts writing output.")

        if refresh_log:
            st.rerun()

    # Show currently running jobs (lockfiles)
    st.markdown("---")
    st.markdown("#### Running Jobs")
    st.caption("Checks for active lockfiles in the backend container.")

    if st.button("Check Running Jobs"):
        try:
            cmd = ["docker", "exec", "skuld-backend", "bash", "-c",
                   "ls -la /tmp/skuld_data_collection_*.lock 2>/dev/null && "
                   "for f in /tmp/skuld_data_collection_*.lock; do "
                   "echo \"$(basename $f .lock): PID=$(cat $f)\"; done"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.stdout.strip():
                st.code(result.stdout, language="bash")
            else:
                st.success("No jobs currently running.")
        except Exception as e:
            st.warning(f"Could not check: {e}")


# ==============================================================================
# TAB 3: RECENT ACTIVITY (from DataChangeLogs)
# ==============================================================================
with tab_activity:
    st.markdown("#### Recent Data Operations")

    # Time range filter
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
