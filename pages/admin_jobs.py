"""
Admin page for job management and log downloading.
"""
import http.client
import json as json_lib
import logging
import socket
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

LOGS_BASE = Path(__file__).resolve().parent.parent / "logs"

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
    "historical_dividend_classification",
    "historical_full",
    "historization",
    "only_run_migrations",
    "sp500_constituents",
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
    "historical_dividend_classification": "Backfill Dividend Classification",
    "historical_full": "Full historical backfill (prices -> technicals -> IV, sequential)",
    "historization": "Archive/version current data",
    "only_run_migrations": "Run DB migrations only (no data collection)",
}


# ==============================================================================
# Docker Engine API helpers (via Unix socket)
# ==============================================================================

class DockerUnixConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost")

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect("/var/run/docker.sock")


def _docker_exec_detached(container: str, cmd: list[str]) -> str | None:
    try:
        conn = DockerUnixConnection()
        conn.request("POST", f"/containers/{container}/exec",
                     body=json_lib.dumps({"Cmd": cmd, "Detach": True}),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status != 201:
            return None
        exec_id = json_lib.loads(resp.read().decode())["Id"]

        conn2 = DockerUnixConnection()
        conn2.request("POST", f"/exec/{exec_id}/start",
                      body=json_lib.dumps({"Detach": True}),
                      headers={"Content-Type": "application/json"})
        resp2 = conn2.getresponse()
        resp2.read()
        return exec_id if resp2.status == 200 else None
    except Exception as e:
        logger.warning(f"Docker exec failed: {e}")
        return None


# ==============================================================================
# Page
# ==============================================================================

st.subheader("Admin - Job Management")

tab_jobs, tab_logs = st.tabs(["Trigger Jobs", "Log Files"])


# ==============================================================================
# TAB 1: TRIGGER JOBS
# ==============================================================================
with tab_jobs:
    st.markdown("#### Manually Trigger Jobs")
    st.info("Jobs run inside the **skuld-backend** Docker container via the Docker socket.")

    selected_mode = st.selectbox(
        "Job Mode",
        JOB_MODES,
        format_func=lambda m: f"{m} — {JOB_DESCRIPTIONS.get(m, '')}",
    )

    if st.button("Start Job", type="primary"):
        cmd = ["/bin/bash", "/app/Skuld/run_data_collection.sh", selected_mode]
        exec_id = _docker_exec_detached("skuld-backend", cmd)
        if exec_id:
            st.success(f"Job **{selected_mode}** triggered successfully!")
        else:
            st.error(
                "Failed to trigger job.\n"
                "- Docker socket not mounted (`/var/run/docker.sock`)\n"
                "- `skuld-backend` container not running"
            )


# ==============================================================================
# TAB 2: LOG FILES — browse & download only, no in-page rendering
# ==============================================================================
with tab_logs:
    st.markdown("#### Download Log Files")
    st.caption("Browse the log directory and download files. No in-page rendering to keep things fast.")

    if not LOGS_BASE.exists():
        st.info("No log directories found.")
    else:
        # Component
        components = sorted(
            d.name for d in LOGS_BASE.iterdir()
            if d.is_dir() and d.name != "streamlit"
        )

        if not components:
            st.info("No log components found.")
        else:
            col1, col2, col3 = st.columns(3)

            with col1:
                selected_component = st.selectbox("Component", components)

            component_dir = LOGS_BASE / selected_component
            dates = sorted(
                (d.name for d in component_dir.iterdir() if d.is_dir()),
                reverse=True,
            ) if component_dir.exists() else []

            with col2:
                if dates:
                    selected_date = st.selectbox("Date", dates)
                else:
                    selected_date = None
                    st.warning("No dates available.")

            if selected_date:
                log_dir = component_dir / selected_date
                log_files = sorted(
                    (f for f in log_dir.iterdir() if f.suffix == ".log"),
                    key=lambda f: f.name,
                    reverse=True,
                )

                with col3:
                    if log_files:
                        selected_file = st.selectbox(
                            "Log File",
                            log_files,
                            format_func=lambda f: f"{f.name} ({f.stat().st_size // 1024} KB)",
                        )
                    else:
                        selected_file = None
                        st.warning("No log files for this date.")

                if selected_file:
                    file_bytes = selected_file.read_bytes()
                    st.download_button(
                        label=f"Download {selected_file.name}",
                        data=file_bytes,
                        file_name=selected_file.name,
                        mime="text/plain",
                        type="primary",
                        use_container_width=True,
                    )
                    st.caption(f"Size: {len(file_bytes) // 1024} KB")

        # Full directory listing
        st.markdown("---")
        st.markdown("#### All Log Files")
        st.caption("Full listing — click a component/date to navigate above.")

        rows = []
        for comp_dir in sorted(LOGS_BASE.iterdir()):
            if not comp_dir.is_dir() or comp_dir.name == "streamlit":
                continue
            for date_dir in sorted(comp_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                for lf in sorted(date_dir.iterdir(), reverse=True):
                    if lf.suffix != ".log":
                        continue
                    rows.append({
                        "Component": comp_dir.name,
                        "Date": date_dir.name,
                        "File": lf.name,
                        "Size (KB)": round(lf.stat().st_size / 1024, 1),
                    })

        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
