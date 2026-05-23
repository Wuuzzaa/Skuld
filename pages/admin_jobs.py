"""
Admin page for job management and log viewing.
Allows viewing pipeline logs, triggering jobs manually, and monitoring activity.
Uses the skuld-api container for job triggering and running-job checks.
"""
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import requests
import streamlit as st
import pandas as pd

from src.database import select_into_dataframe

logger = logging.getLogger(__name__)

# Base path for logs (shared Docker volume: ./logs:/app/Skuld/logs)
LOGS_BASE = Path(__file__).resolve().parent.parent / "logs"

# API base URL (skuld-api container on same Docker network)
API_BASE_URL = os.getenv("SKULD_API_URL", "http://skuld-api:8000")

# Available job modes
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


def _get_api_token() -> str | None:
    """Get JWT token from skuld-api using admin credentials."""
    if "api_token" in st.session_state and st.session_state.get("api_token_expiry", datetime.min) > datetime.now():
        return st.session_state["api_token"]

    admin_password = os.getenv("SKULD_ADMIN_PASSWORD", "Kx9$mTr!vQ4pNw2z")
    try:
        resp = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            json={"username": "admin", "password": admin_password},
            timeout=5,
        )
        if resp.status_code == 200:
            token = resp.json()["access_token"]
            st.session_state["api_token"] = token
            st.session_state["api_token_expiry"] = datetime.now() + timedelta(hours=12)
            return token
    except Exception as e:
        logger.warning(f"Failed to get API token: {e}")
    return None


def _api_headers() -> dict:
    """Get authorization headers for API calls."""
    token = _get_api_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _api_get(path: str, params: dict = None) -> requests.Response | None:
    """Make authenticated GET request to skuld-api."""
    try:
        return requests.get(
            f"{API_BASE_URL}/api/admin{path}",
            headers=_api_headers(),
            params=params,
            timeout=15,
        )
    except Exception as e:
        logger.warning(f"API GET {path} failed: {e}")
        return None


def _api_post(path: str, json_data: dict = None) -> requests.Response | None:
    """Make authenticated POST request to skuld-api."""
    try:
        return requests.post(
            f"{API_BASE_URL}/api/admin{path}",
            headers=_api_headers(),
            json=json_data,
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"API POST {path} failed: {e}")
        return None


st.subheader("Admin - Job Management")

tab_logs, tab_jobs, tab_activity = st.tabs(["Log Viewer", "Trigger Jobs", "Recent Activity"])

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
        "Triggering from here calls the **skuld-api** which executes via Docker socket."
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
                resp = _api_post("/jobs/trigger", {"mode": selected_mode})
                if resp and resp.status_code == 200:
                    data = resp.json()
                    st.success(f"Job **{selected_mode}** triggered successfully!")
                    # Set up live log tracking
                    st.session_state.live_log_active = True
                    st.session_state.live_log_component = data.get("component", "data_collector")
                    st.session_state.live_log_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
                    st.session_state.live_log_filename = data.get("filename", "")
                    st.session_state.live_log_mode = selected_mode
                    st.session_state.live_log_since_line = 0
                    st.session_state.live_log_retry_count = 0
                elif resp:
                    detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                    st.error(f"Failed to trigger job: {detail}")
                else:
                    st.error("Failed to reach skuld-api. Is the API container running?")

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
                # Try finding actual latest file via API or local filesystem
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
    st.caption("Checks for active lockfiles in the backend container via API.")

    if st.button("Check Running Jobs"):
        resp = _api_get("/jobs/running")
        if resp and resp.status_code == 200:
            running = resp.json()
            if running:
                for job in running:
                    status_icon = "🟢" if job.get("alive") else "🔴"
                    st.write(f"{status_icon} **{job['mode']}** — PID {job['pid']} ({'running' if job.get('alive') else 'stale lockfile'})")
            else:
                st.success("No jobs currently running.")
        elif resp:
            st.warning(f"API returned {resp.status_code}")
        else:
            st.warning("Could not reach skuld-api to check running jobs.")


# ==============================================================================
# TAB 3: RECENT ACTIVITY (from DataChangeLogs)
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
