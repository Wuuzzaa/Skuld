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

tab_jobs, tab_status, tab_logs = st.tabs(["Trigger Jobs", "Job Status", "Log Files"])


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
# TAB 2: JOB STATUS — one row per finished job, read from logs/_status/*.jsonl
# Written by run_data_collection.sh at job end (captures OK/FAIL/OOM/TIMEOUT/
# SKIPPED, even for killed jobs). No per-log parsing → stays fast.
# ==============================================================================
STATUS_DIR = LOGS_BASE / "_status"

STATUS_STYLE = {
    "OK": "🟢 OK",
    "FAIL": "🔴 FAIL",
    "OOM": "🔴 OOM",
    "TIMEOUT": "🟠 TIMEOUT",
    "SKIPPED": "⚪ SKIPPED",
}


def _load_status_rows(days: int) -> list[dict]:
    """Read the most recent `days` JSONL status files, newest first."""
    if not STATUS_DIR.exists():
        return []
    files = sorted(
        (f for f in STATUS_DIR.iterdir() if f.suffix == ".jsonl"),
        reverse=True,
    )[:days]
    rows: list[dict] = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json_lib.loads(line))
            except json_lib.JSONDecodeError:
                continue  # skip a corrupt/partial line, keep the rest
    return rows


with tab_status:
    st.markdown("#### Job Status")
    st.caption(
        "One line per finished job, written when the job ends "
        "(covers crashes, OOM and timeouts too). Auto-deleted after 14 days."
    )

    if not STATUS_DIR.exists():
        st.info(
            "No status entries yet. The status log fills up once jobs run "
            "with the updated `run_data_collection.sh`."
        )
    else:
        col_a, col_b = st.columns([1, 3])
        with col_a:
            days = st.selectbox("Time range (days)", [1, 3, 7, 14], index=2)

        rows = _load_status_rows(days)

        if not rows:
            st.info("No status entries in the selected range.")
        else:
            import pandas as pd

            df = pd.DataFrame(rows)
            # Newest first by timestamp.
            if "ts" in df.columns:
                df = df.sort_values("ts", ascending=False, kind="stable")

            # Summary counts per status.
            counts = df["status"].value_counts().to_dict()
            metric_cols = st.columns(5)
            for i, key in enumerate(["OK", "FAIL", "OOM", "TIMEOUT", "SKIPPED"]):
                metric_cols[i].metric(STATUS_STYLE[key].split(" ", 1)[-1], counts.get(key, 0))

            with col_b:
                mode_options = ["(all)"] + sorted(df["mode"].dropna().unique().tolist())
                sel_mode = st.selectbox("Filter by mode", mode_options)
            if sel_mode != "(all)":
                df = df[df["mode"] == sel_mode]

            # Pretty display columns.
            disp = df.copy()
            disp["status"] = disp["status"].map(lambda s: STATUS_STYLE.get(s, s))
            if "duration_s" in disp.columns:
                disp["duration"] = disp["duration_s"].map(
                    lambda s: f"{int(s) // 3600}h {int(s) % 3600 // 60}m {int(s) % 60}s"
                    if pd.notna(s) else ""
                )
            keep = [c for c in ["ts", "mode", "status", "duration", "exit_code", "note"] if c in disp.columns]
            st.dataframe(
                disp[keep],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ts": "Time (UTC)",
                    "mode": "Mode",
                    "status": "Status",
                    "duration": "Duration",
                    "exit_code": "Exit",
                    "note": "Note",
                },
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
            if d.is_dir() and d.name not in ("streamlit", "_status")
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
            if not comp_dir.is_dir() or comp_dir.name in ("streamlit", "_status"):
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
