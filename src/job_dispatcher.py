"""Job-Scheduler — SM36/SM37-Stil Sicherheitsnetz gegen versehentlichen Job-Start.

Statt Jobs per Klick sofort zu feuern, landen sie als JSON-Datei in einer dateibasierten
Queue unter ``logs/_queue/``. Ein Cron-Dispatcher (diese Datei als ``__main__``, jede Minute)
startet fällige Jobs über die bestehende ``run_data_collection.sh``-Kette.

Design: docs/superpowers/specs/2026-07-24-job-scheduler-design.md

Queue-Datei-Namen kodieren den Status, damit "Claiming" atomar per ``os.rename`` geht:
    <run_at_iso>__<mode>__<id>.<status>.json    status ∈ {geplant, laufend}

Reiner Filesystem-Code (kein DB, kein Docker) → unit-testbar.
"""
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Modi, die db_setup() (drop/recreate Views) + destruktive TRUNCATEs auslösen.
# Sie verlangen auf der Admin-Page einen Typing-Confirm vor dem Einplanen.
DESTRUCTIVE_MODES = {"all", "historical_full", "only_run_migrations"}

# Queue-Wurzel: gleiches Muster wie admin_jobs.py (logs neben dem Repo-Root).
QUEUE_DIR = Path(__file__).resolve().parent.parent / "logs" / "_queue"

# Wrapper-Skript, das schon Lock/Timeout/write_status/Telegram kapselt.
RUN_SCRIPT = "/app/Skuld/run_data_collection.sh"

_ISO = "%Y-%m-%dT%H:%M:%SZ"


# ==========================================================================
# Helpers
# ==========================================================================
def _fmt_ts(dt: datetime) -> str:
    """UTC-ISO ohne Mikrosekunden, mit 'Z'."""
    return dt.astimezone(timezone.utc).strftime(_ISO)


def _parse_ts(s: str) -> datetime:
    return datetime.strptime(s, _ISO).replace(tzinfo=timezone.utc)


def _safe(part: str) -> str:
    """Modus/ID sicher für einen Dateinamen machen (keine Trenner/Punkte)."""
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in part)


def _job_path(qdir: Path, job: dict, status: str) -> Path:
    stamp = job["run_at"].replace(":", "-")  # ':' ist auf Windows kein gültiges Namenszeichen
    return qdir / f"{stamp}__{_safe(job['mode'])}__{job['id']}.{status}.json"


def _find_by_id(qdir: Path, job_id: str, status: str | None = None) -> Path | None:
    pattern = f"*__{job_id}.{status}.json" if status else f"*__{job_id}.*.json"
    matches = sorted(qdir.glob(pattern))
    return matches[0] if matches else None


def _quarantine(qdir: Path, f: Path) -> None:
    """Korrupte Datei beiseiteschieben, damit der Rest der Queue weiterläuft."""
    corrupt = qdir / "_corrupt"
    corrupt.mkdir(exist_ok=True)
    try:
        f.rename(corrupt / f.name)
    except OSError:
        logger.warning("Konnte korrupte Queue-Datei nicht verschieben: %s", f)


def _read(f: Path, qdir: Path) -> dict | None:
    """JSON lesen; bei kaputter Datei quarantänen und None liefern (kein Raise)."""
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        data["status"] = f.name.rsplit(".", 2)[1]  # Status aus Dateiname = Wahrheit
        return data
    except (json.JSONDecodeError, KeyError, IndexError, OSError) as e:
        logger.warning("Korrupte Queue-Datei %s übersprungen: %s", f.name, e)
        _quarantine(qdir, f)
        return None


# ==========================================================================
# Public queue API
# ==========================================================================
def enqueue_job(qdir: Path, mode: str, run_at: datetime, created_by: str) -> dict:
    """Neuen Job als 'geplant'-Datei schreiben. Atomar via temp + rename."""
    qdir.mkdir(parents=True, exist_ok=True)
    job = {
        "id": uuid.uuid4().hex[:8],
        "mode": mode,
        "run_at": _fmt_ts(run_at),
        "created_at": _fmt_ts(datetime.now(timezone.utc)),
        "created_by": created_by,
        "status": "geplant",
    }
    dest = _job_path(qdir, job, "geplant")
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(dest)  # atomar auf gleichem Filesystem
    logger.info("Job eingeplant: %s %s @ %s", job["id"], mode, job["run_at"])
    return job


def list_jobs(qdir: Path) -> list[dict]:
    """Alle Queue-Jobs (geplant + laufend), neueste run_at zuerst."""
    if not qdir.exists():
        return []
    jobs = []
    for f in qdir.glob("*.json"):
        if f.name.endswith(".json.tmp"):
            continue
        data = _read(f, qdir)
        if data:
            jobs.append(data)
    return sorted(jobs, key=lambda j: j.get("run_at", ""), reverse=True)


def due_jobs(qdir: Path, now: datetime) -> list[dict]:
    """Nur fällige 'geplant'-Jobs (run_at <= now). 'laufend' + Zukunft werden ignoriert."""
    out = []
    for job in list_jobs(qdir):
        if job["status"] != "geplant":
            continue
        try:
            if _parse_ts(job["run_at"]) <= now.astimezone(timezone.utc):
                out.append(job)
        except (ValueError, KeyError):
            continue
    return sorted(out, key=lambda j: j["run_at"])  # älteste zuerst


def claim_job(qdir: Path, job_id: str) -> dict | None:
    """Atomar 'geplant' -> 'laufend' umbenennen. None wenn schon geclaimt (kein Doppelstart)."""
    src = _find_by_id(qdir, job_id, "geplant")
    if src is None:
        return None
    data = _read(src, qdir)
    if data is None:
        return None
    data["status"] = "laufend"
    dest = _job_path(qdir, data, "laufend")
    try:
        os.rename(src, dest)  # atomar; wirft wenn src schon weg ist
    except OSError:
        return None
    return data


def cancel_job(qdir: Path, job_id: str) -> bool:
    """Geplanten Job löschen. Laufende Jobs sind nicht stornierbar → False."""
    src = _find_by_id(qdir, job_id, "geplant")
    if src is None:
        return False
    try:
        src.unlink()
        return True
    except OSError:
        return False


def _finish(qdir: Path, job_id: str) -> None:
    """'laufend'-Datei entfernen — ab hier trackt sich der Job via logs/_status/ selbst."""
    f = _find_by_id(qdir, job_id, "laufend")
    if f:
        try:
            f.unlink()
        except OSError:
            pass


# ==========================================================================
# Dispatcher (Cron ruft das jede Minute)
# ==========================================================================
def run_dispatch(qdir: Path = QUEUE_DIR, now: datetime | None = None) -> int:
    """Fällige Jobs starten. Gibt die Anzahl gestarteter Jobs zurück.

    Läuft IM skuld-backend-Container → ruft run_data_collection.sh lokal auf
    (kein Docker-Socket nötig, anders als die Admin-Page). Startet detached,
    entfernt danach die laufend-Datei.
    """
    now = now or datetime.now(timezone.utc)
    started = 0
    for job in due_jobs(qdir, now):
        claimed = claim_job(qdir, job["id"])
        if claimed is None:
            continue  # anderer Dispatcher-Lauf war schneller
        try:
            subprocess.Popen(
                ["/bin/bash", RUN_SCRIPT, claimed["mode"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,  # überlebt den Dispatcher-Prozess
            )
            logger.info("Dispatcher startete Job %s (%s)", claimed["id"], claimed["mode"])
            started += 1
        except OSError as e:
            logger.error("Job-Start fehlgeschlagen (%s): %s — zurück auf geplant", claimed["mode"], e)
            # Claim zurückrollen: laufend -> geplant, damit der Job erneut versucht wird.
            back = _find_by_id(qdir, claimed["id"], "laufend")
            if back:
                claimed["status"] = "geplant"
                back.rename(_job_path(qdir, claimed, "geplant"))
            continue
        _finish(qdir, claimed["id"])
    return started


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = run_dispatch()
    if n:
        logger.info("Dispatcher: %d Job(s) gestartet", n)
    sys.exit(0)
