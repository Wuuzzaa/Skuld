"""
Admin page for job management and log downloading.
"""
import json as json_lib
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

from src.job_dispatcher import (
    DESTRUCTIVE_MODES,
    QUEUE_DIR,
    cancel_job,
    enqueue_job,
    list_jobs,
)

logger = logging.getLogger(__name__)

LOGS_BASE = Path(__file__).resolve().parent.parent / "logs"

# Ordner unter logs/, die KEINE herunterladbaren .log-Dateien enthalten und
# daher nicht als "Component" im Log-Browser auftauchen dürfen:
#   streamlit = Streamlit-interne Logs, _status = Job-Status-JSONL (eigener Tab),
#   _queue    = Job-Scheduler-Queue (JSON-Jobs, kein date/-Unterordner).
NON_LOG_DIRS = {"streamlit", "_status", "_queue"}

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
# Helpers
# ==============================================================================

def _tail_lines(path: Path, n: int) -> list[str]:
    """Return the last `n` lines without reading the whole file into memory."""
    with path.open("rb") as fh:
        chunk = 65536
        fh.seek(0, 2)
        remaining = fh.tell()
        buf = b""
        lines_found = 0
        while remaining > 0 and lines_found <= n:
            read_size = min(chunk, remaining)
            remaining -= read_size
            fh.seek(remaining)
            buf = fh.read(read_size) + buf
            lines_found = buf.count(b"\n")
    all_lines = buf.decode("utf-8", errors="replace").splitlines()
    return all_lines[-n:] if len(all_lines) > n else all_lines


# ==============================================================================
# Page
# ==============================================================================

st.subheader("Admin - Job Management")

tab_jobs, tab_status, tab_logs = st.tabs(["Trigger Jobs", "Job Status", "Log Files"])


# ==============================================================================
# TAB 1: TRIGGER JOBS — jetzt Schedule-Queue (SM37-Stil), kein Sofort-Feuer mehr.
# Der Button plant den Job in logs/_queue/ ein; ein Cron-Dispatcher startet ihn
# im Minutentakt. Destruktive Modi verlangen einen Typing-Confirm.
# ==============================================================================
with tab_jobs:
    st.markdown("#### Job einplanen")
    st.info(
        "Jobs werden **eingeplant** statt sofort gestartet. Ein Dispatcher im "
        "**skuld-backend**-Container prüft die Queue jede Minute und startet fällige Jobs. "
        "Geplante Jobs sind unten stornierbar, bis sie laufen."
    )

    selected_mode = st.selectbox(
        "Job Mode",
        JOB_MODES,
        format_func=lambda m: f"{m} — {JOB_DESCRIPTIONS.get(m, '')}",
    )

    is_destructive = selected_mode in DESTRUCTIVE_MODES

    col_when, col_time = st.columns([1, 2])
    with col_when:
        when = st.radio("Ausführung", ["Jetzt", "Zu Uhrzeit (UTC)"], horizontal=False)
    run_at = datetime.now(timezone.utc)
    with col_time:
        if when == "Zu Uhrzeit (UTC)":
            d = st.date_input("Datum (UTC)", value=datetime.now(timezone.utc).date())
            t = st.time_input("Uhrzeit (UTC)", value=(datetime.now(timezone.utc) + timedelta(minutes=5)).time())
            run_at = datetime.combine(d, t, tzinfo=timezone.utc)

    confirmed = True
    if is_destructive:
        st.warning(
            f"⚠️ **`{selected_mode}`** ist ein **destruktiver** Modus "
            "(setzt DB-Views neu auf und/oder überschreibt Massendaten via TRUNCATE). "
            "Zum Bestätigen den Modusnamen exakt eintippen."
        )
        typed = st.text_input(f"Zur Bestaetigung '{selected_mode}' eingeben", key="destructive_confirm")
        confirmed = typed.strip() == selected_mode

    if st.button("Einplanen", type="primary", disabled=not confirmed):
        try:
            job = enqueue_job(QUEUE_DIR, mode=selected_mode, run_at=run_at, created_by="admin-page")
            when_txt = "jetzt (nächster Minutentakt)" if when == "Jetzt" else f"um {job['run_at']}"
            st.success(f"Job **{selected_mode}** eingeplant — läuft {when_txt}. (ID `{job['id']}`)")
        except OSError as e:
            st.error(f"Konnte Job nicht einplanen: {e}")

    # -----------------------------------------------------------------
    # Geplante Jobs — Queue-Übersicht + Stornieren
    # -----------------------------------------------------------------
    st.markdown("---")
    st.markdown("#### Geplante Jobs")
    st.caption("Einträge aus der Queue (`logs/_queue/`). Geplante Jobs sind stornierbar, laufende nicht.")

    queued = list_jobs(QUEUE_DIR)
    if not queued:
        st.info("Keine geplanten oder laufenden Jobs.")
    else:
        status_icon = {"geplant": "🕒 geplant", "laufend": "▶️ laufend"}
        for job in queued:
            c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
            c1.markdown(f"**{job.get('mode', '?')}**")
            c2.markdown(status_icon.get(job.get("status"), job.get("status", "?")))
            c3.caption(f"run_at {job.get('run_at', '?')} · von {job.get('created_by', '?')} · `{job.get('id', '?')}`")
            if job.get("status") == "geplant":
                if c4.button("Stornieren", key=f"cancel_{job['id']}"):
                    if cancel_job(QUEUE_DIR, job["id"]):
                        st.success(f"Job `{job['id']}` storniert.")
                        st.rerun()
                    else:
                        st.warning(f"Job `{job['id']}` konnte nicht storniert werden (läuft evtl. schon).")


# ==============================================================================
# TAB 2: JOB STATUS — one row per finished job, read from logs/_status/*.jsonl
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
                continue
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
            if "ts" in df.columns:
                df = df.sort_values("ts", ascending=False, kind="stable")

            counts = df["status"].value_counts().to_dict()
            metric_cols = st.columns(5)
            for i, key in enumerate(["OK", "FAIL", "OOM", "TIMEOUT", "SKIPPED"]):
                metric_cols[i].metric(STATUS_STYLE[key].split(" ", 1)[-1], counts.get(key, 0))

            with col_b:
                mode_options = ["(all)"] + sorted(df["mode"].dropna().unique().tolist())
                sel_mode = st.selectbox("Filter by mode", mode_options)
            if sel_mode != "(all)":
                df = df[df["mode"] == sel_mode]

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
# TAB 3: LOG FILES — browse, view in-browser, and download
# ==============================================================================
with tab_logs:
    st.markdown("#### Log Files")

    if not LOGS_BASE.exists():
        st.info("No log directories found.")
    else:
        components = sorted(
            d.name for d in LOGS_BASE.iterdir()
            if d.is_dir() and d.name not in NON_LOG_DIRS
        )

        if not components:
            st.info("No log components found.")
        else:
            col1, col2, col3 = st.columns(3)

            with col1:
                selected_component = st.selectbox("Component", components, key="lv_component")

            component_dir = LOGS_BASE / selected_component
            dates = sorted(
                (d.name for d in component_dir.iterdir() if d.is_dir()),
                reverse=True,
            ) if component_dir.exists() else []

            with col2:
                if dates:
                    selected_date = st.selectbox("Date", dates, key="lv_date")
                else:
                    selected_date = None
                    st.warning("No dates available.")

            selected_file = None
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
                            key="lv_file",
                        )
                    else:
                        st.warning("No log files for this date.")

            # ------------------------------------------------------------------
            # Viewer + Download
            # ------------------------------------------------------------------
            if selected_file:
                file_size_kb = selected_file.stat().st_size // 1024

                vcol1, vcol2, vcol3 = st.columns([2, 3, 2])
                with vcol1:
                    tail_n = st.selectbox(
                        "Lines to show (tail)",
                        [100, 250, 500, 1000, 2000],
                        index=1,
                        key="lv_tail",
                    )
                with vcol2:
                    filter_text = st.text_input(
                        "Filter (contains, case-insensitive)",
                        key="lv_filter",
                        placeholder="ERROR, WARNING, ...",
                    )
                with vcol3:
                    st.markdown("<div style='margin-top:28px'>", unsafe_allow_html=True)
                    st.download_button(
                        label=f"Download ({file_size_kb} KB)",
                        data=selected_file.read_bytes(),
                        file_name=selected_file.name,
                        mime="text/plain",
                        use_container_width=True,
                        key="lv_download",
                    )
                    st.markdown("</div>", unsafe_allow_html=True)

                lines = _tail_lines(selected_file, tail_n)

                if filter_text.strip():
                    needle = filter_text.strip().lower()
                    lines = [ln for ln in lines if needle in ln.lower()]

                # Count total lines without loading full file
                with selected_file.open("rb") as _fh:
                    total_lines = sum(1 for _ in _fh)

                matched_info = f" · {len(lines)} match filter" if filter_text.strip() else ""
                st.caption(
                    f"{selected_file.name} · {file_size_kb} KB · "
                    f"{total_lines:,} total lines · showing last {tail_n}"
                    + matched_info
                )

                st.code("\n".join(lines) if lines else "(no matching lines)", language="log")

        # ----------------------------------------------------------------------
        # Full directory listing — row-select + download (unchanged)
        # ----------------------------------------------------------------------
        st.markdown("---")
        st.markdown("#### All Log Files")
        st.caption("Zeile anklicken → Download-Button erscheint darunter.")

        all_rows = []
        for comp_dir in sorted(LOGS_BASE.iterdir()):
            if not comp_dir.is_dir() or comp_dir.name in NON_LOG_DIRS:
                continue
            for date_dir in sorted(comp_dir.iterdir(), reverse=True):
                if not date_dir.is_dir():
                    continue
                for lf in sorted(date_dir.iterdir(), reverse=True):
                    if lf.suffix != ".log":
                        continue
                    all_rows.append({
                        "Component": comp_dir.name,
                        "Date": date_dir.name,
                        "File": lf.name,
                        "Size (KB)": round(lf.stat().st_size / 1024, 1),
                        "_path": str(lf),
                    })

        if all_rows:
            import pandas as pd

            all_df = pd.DataFrame(all_rows)
            event = st.dataframe(
                all_df.drop(columns=["_path"]),
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key="all_logs_table",
            )

            sel_rows = event.selection.rows if event and event.selection else []
            if sel_rows:
                picked = all_df.iloc[sel_rows[0]]
                picked_path = Path(picked["_path"])
                if picked_path.exists():
                    data = picked_path.read_bytes()
                    st.download_button(
                        label=f"⬇️ Download {picked['Component']}/{picked['Date']}/{picked['File']} "
                              f"({len(data) // 1024} KB)",
                        data=data,
                        file_name=picked["File"],
                        mime="text/plain",
                        type="primary",
                        use_container_width=True,
                        key="all_logs_download",
                    )
                else:
                    st.warning("Datei nicht mehr vorhanden (evtl. durch Log-Rotation gelöscht).")
            else:
                st.caption("↑ Eine Zeile auswählen, um sie herunterzuladen.")
        else:
            st.info("Keine Log-Dateien gefunden.")
