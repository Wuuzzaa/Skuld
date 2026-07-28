"""
SKULD Health Sidecar
====================

Tiny stdlib HTTP server that exposes deeper health/version info than the
Streamlit `/_stcore/health` endpoint. Designed to be probed by Uptime Kuma
on the internal `web` network.

Endpoints
---------
- GET /version       -> {"version": "...", "branch": "...", "commit": "..."}
- GET /health        -> 200 if everything OK, 503 otherwise.
                        body: {"db_ok": bool, "disk_free_pct": float,
                               "last_cron_age_s": int|null,
                               "checks": {"db": "...", "disk": "...", "cron": "..."}}
- GET /health/cron   -> 200 if last cron logfile mtime < CRON_MAX_AGE_S, else 503

Design
------
- No FastAPI/uvicorn dependency: stdlib only. Reuses the existing
  `skuld-app-image` so we don't add a build step.
- DB check uses the same SQLAlchemy engine that the rest of the codebase
  builds in `src/database.py`; that means we automatically pick up the
  same connection params, pooling, and SSH-tunnel logic.
- Disk check looks at the volume that holds /app/Skuld/logs (the bind mount
  shared with both frontend and backend).
- Cron heartbeat: newest mtime under /app/Skuld/logs is treated as the
  "last cron activity" timestamp.

Run
---
    python -m health.server         # default port 8800
    HEALTH_PORT=9000 python -m health.server
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any

LOG = logging.getLogger("skuld.health")

# Resolve repo root so this module works whether launched as `python -m health.server`
# or from inside the container.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Defer heavy imports so the module imports cleanly even if e.g. SQLAlchemy
# is missing (tests, lint runs).
try:
    from config import VERSION  # noqa: E402
except Exception:  # pragma: no cover - defensive
    VERSION = os.getenv("SKULD_VERSION", "unknown")

# --- Tunables (env-driven so we don't hard-code prod values) -----------------
HEALTH_PORT = int(os.getenv("HEALTH_PORT", "8800"))
HEALTH_HOST = os.getenv("HEALTH_HOST", "0.0.0.0")  # bind to all in container
LOGS_DIR = Path(os.getenv("HEALTH_LOGS_DIR", "/app/Skuld/logs"))
DISK_PATH = os.getenv("HEALTH_DISK_PATH", "/app/Skuld/logs")
DISK_MIN_FREE_PCT = float(os.getenv("HEALTH_DISK_MIN_FREE_PCT", "10"))
CRON_MAX_AGE_S = int(os.getenv("HEALTH_CRON_MAX_AGE_S", str(26 * 3600)))  # 26h
DB_TIMEOUT_S = float(os.getenv("HEALTH_DB_TIMEOUT_S", "3"))


# --- Individual checks -------------------------------------------------------
def check_db() -> tuple[bool, str]:
    """`SELECT 1` against Postgres via the shared engine. Returns (ok, detail)."""
    try:
        # Imported lazily so a broken DB config can't break /version.
        from src.database import get_postgres_engine  # type: ignore
        from sqlalchemy import text
    except Exception as exc:  # pragma: no cover
        return False, f"import-failed: {exc}"

    try:
        engine = get_postgres_engine()
        if engine is None:
            return False, "engine-none (no POSTGRES_DB?)"
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:
        return False, f"query-failed: {exc.__class__.__name__}: {exc}"


def check_disk() -> tuple[bool, float, str]:
    """Returns (ok, free_pct, detail)."""
    try:
        usage = shutil.disk_usage(DISK_PATH)
        free_pct = (usage.free / usage.total) * 100.0 if usage.total else 0.0
        ok = free_pct >= DISK_MIN_FREE_PCT
        detail = f"{free_pct:.1f}% free of {usage.total // (1024**3)} GiB"
        return ok, free_pct, detail
    except FileNotFoundError:
        return False, 0.0, f"path-missing: {DISK_PATH}"
    except Exception as exc:  # pragma: no cover
        return False, 0.0, f"stat-failed: {exc}"


def check_cron() -> tuple[bool, int | None, str]:
    """
    Newest mtime under LOGS_DIR. Returns (ok, age_seconds, detail).
    "ok" means we have *some* recent log activity. age_seconds is None if no
    log files were found at all.
    """
    if not LOGS_DIR.exists():
        return False, None, f"logs-dir-missing: {LOGS_DIR}"

    newest_mtime = 0.0
    for p in LOGS_DIR.rglob("*.log"):
        try:
            m = p.stat().st_mtime
            if m > newest_mtime:
                newest_mtime = m
        except OSError:
            continue

    if newest_mtime == 0.0:
        return False, None, "no-log-files"

    age_s = int(time.time() - newest_mtime)
    ok = age_s < CRON_MAX_AGE_S
    detail = f"newest log {age_s}s ago"
    return ok, age_s, detail


# --- HTTP handler ------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    server_version = "SkuldHealth/1.0"

    # Silence the default "GET /health HTTP/1.1" 200 - per-request stdout spam.
    def log_message(self, fmt: str, *args: Any) -> None:
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    # --- response helpers ---
    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        # Cache-Control so Kuma never gets a stale value.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # --- routes ---
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler convention)
        path = self.path.split("?", 1)[0].rstrip("/") or "/"

        if path == "/version":
            self._send_json(
                200,
                {
                    "version": str(VERSION),
                    "branch": os.getenv("SKULD_BRANCH", "unknown"),
                    "commit": os.getenv("SKULD_COMMIT", os.getenv("SKULD_VERSION", "")),
                },
            )
            return

        if path == "/health":
            db_ok, db_detail = check_db()
            disk_ok, disk_pct, disk_detail = check_disk()
            cron_ok, cron_age, cron_detail = check_cron()

            overall_ok = db_ok and disk_ok and cron_ok
            status = 200 if overall_ok else 503
            self._send_json(
                status,
                {
                    "ok": overall_ok,
                    "db_ok": db_ok,
                    "disk_free_pct": round(disk_pct, 2),
                    "last_cron_age_s": cron_age,
                    "checks": {
                        "db": db_detail,
                        "disk": disk_detail,
                        "cron": cron_detail,
                    },
                },
            )
            return

        if path == "/health/cron":
            cron_ok, cron_age, cron_detail = check_cron()
            self._send_json(
                200 if cron_ok else 503,
                {"ok": cron_ok, "age_s": cron_age, "detail": cron_detail},
            )
            return

        # Unknown route -> 404 JSON, easier to debug than HTML.
        self._send_json(404, {"error": "not-found", "path": path})


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded so a slow DB probe doesn't queue up healthchecks."""

    daemon_threads = True
    allow_reuse_address = True


def main() -> None:
    logging.basicConfig(
        level=os.getenv("HEALTH_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    LOG.info("SKULD health sidecar listening on %s:%d", HEALTH_HOST, HEALTH_PORT)
    LOG.info(
        "Tunables: logs=%s disk=%s min_free=%.1f%% cron_max_age=%ds",
        LOGS_DIR, DISK_PATH, DISK_MIN_FREE_PCT, CRON_MAX_AGE_S,
    )
    server = _ThreadingHTTPServer((HEALTH_HOST, HEALTH_PORT), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("shutting down")
        server.server_close()


if __name__ == "__main__":
    main()
