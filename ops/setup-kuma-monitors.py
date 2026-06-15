#!/usr/bin/env python3
"""
setup-kuma-monitors.py
======================

Idempotent provisioning script for Uptime Kuma. Runs against an existing
Kuma instance (already past the setup wizard) and ensures:

  1. A Telegram notification channel ("Telegram (SKULD)") exists, default-
     enabled on all new monitors.
  2. The eight standard SKULD monitors exist (see ops/MONITORING.md).

Re-runs are safe: monitors and the notification are matched by *name*; if
the name already exists the entry is left untouched. Use --force to update
existing entries (delete + recreate).

Quick start
-----------
    pip install uptime-kuma-api
    export KUMA_URL=https://monitoring.skuld-options.com
    export KUMA_USER=admin
    export KUMA_PASS=<your kuma password>
    export TELEGRAM_BOT_TOKEN=<copy from server .env>
    export TELEGRAM_CHAT_ID=-1003610692224
    python ops/setup-kuma-monitors.py

If KUMA_URL is the public Authelia-protected URL, you also need
`KUMA_AUTHELIA_COOKIE`: log in once in your browser, copy the
`authelia_session` cookie value, paste it as the env var.

For a local/internal run from the server itself (recommended), point at the
container directly to skip Authelia entirely:

    ssh deploy@91.98.156.116
    docker run --rm --network=web -e KUMA_URL=http://uptime-kuma:3001 \\
       -e KUMA_USER=admin -e KUMA_PASS=... -e TELEGRAM_BOT_TOKEN=... \\
       -e TELEGRAM_CHAT_ID=... -v /opt/skuld/ops:/work python:3.12-slim \\
       sh -c 'pip install uptime-kuma-api && python /work/setup-kuma-monitors.py'

Design
------
- Monitor specs live in MONITORS below as plain dicts. Easy to diff in code
  review, easy to extend.
- Status codes are passed as the list-of-strings format Kuma expects
  (["200-299"], not "200-299").
- Each monitor that needs Telegram references it by the constant
  `TELEGRAM_NAME`; we resolve that to its DB id at provisioning time.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any

try:
    from uptime_kuma_api import UptimeKumaApi, MonitorType, NotificationType
except ImportError:
    print("ERROR: uptime-kuma-api not installed. Run: pip install uptime-kuma-api", file=sys.stderr)
    sys.exit(2)


# ─── Configuration ──────────────────────────────────────────────────────────
TELEGRAM_NAME = "Telegram (SKULD)"


@dataclass
class MonitorSpec:
    """Plain spec for one Kuma monitor; mapped to API kwargs at apply time."""

    name: str
    type: MonitorType
    extra: dict[str, Any] = field(default_factory=dict)
    interval: int = 60
    retry_interval: int = 60
    max_retries: int = 2
    timeout: int = 10
    description: str = ""
    accepted_codes: list[str] = field(default_factory=lambda: ["200-299"])
    expiry_notification: bool = False
    notify_telegram: bool = True


# Order matters only for human readability in the Kuma dashboard.
MONITORS: list[MonitorSpec] = [
    # ── Internal probes (probed via the docker `web` network) ──
    MonitorSpec(
        name="Health Sidecar - Version",
        type=MonitorType.KEYWORD,
        extra={"url": "http://skuld-health:8800/version", "keyword": "version"},
        description="Internal stdlib HTTP sidecar exposing /version. See ops/MONITORING.md.",
    ),
    MonitorSpec(
        name="Health Sidecar - Full",
        type=MonitorType.KEYWORD,
        extra={"url": "http://skuld-health:8800/health", "keyword": '"ok": true'},
        description="DB + disk + cron-heartbeat. Returns 503 on any sub-check failure.",
        accepted_codes=["200-299"],
    ),
    MonitorSpec(
        name="Streamlit (intern)",
        type=MonitorType.HTTP,
        extra={"url": "http://skuld-frontend:8501/_stcore/health"},
        description="Streamlit's built-in process-level healthcheck.",
    ),
    MonitorSpec(
        name="Postgres",
        type=MonitorType.PORT,
        extra={"hostname": "postgres_setup-db-1", "port": 5432},
        description="TCP reachability of the Postgres container. No actual query is run.",
    ),
    MonitorSpec(
        name="Authelia",
        type=MonitorType.HTTP,
        extra={"url": "http://authelia:9091/api/health"},
        description="Authelia health endpoint. If down, every authenticated route 502s.",
    ),
    # ── External probes (through Cloudflare) ──
    MonitorSpec(
        name="App (extern)",
        type=MonitorType.KEYWORD,
        extra={"url": "https://app.skuld-options.com", "keyword": "Authelia"},
        # 302 to authelia is the *expected* response when not logged in.
        accepted_codes=["200-299", "300-399"],
        expiry_notification=True,
        description="External path: Cloudflare → Traefik → Authelia. Expects redirect to auth.",
    ),
    MonitorSpec(
        name="Massive.com API",
        type=MonitorType.HTTP,
        extra={"url": "https://api.massive.com/v3"},
        interval=300,
        # 401/403/404 are also fine — the API answering at all means it's up.
        accepted_codes=["200-299", "401", "403", "404"],
        description="External data provider. If down, cron jobs collect nothing.",
    ),
    MonitorSpec(
        name="Telegram (selftest)",
        type=MonitorType.HTTP,
        extra={"url": "https://api.telegram.org"},
        interval=600,
        accepted_codes=["200-299", "404"],
        description="Sanity check for the Telegram API itself.",
    ),
]


# ─── Helpers ────────────────────────────────────────────────────────────────
def _required_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        sys.exit(f"ERROR: env var {name} is required (see file docstring).")
    return v


def _ensure_telegram(api: UptimeKumaApi, force: bool) -> int:
    """Create or update the Telegram notification. Returns its id."""
    bot_token = _required_env("TELEGRAM_BOT_TOKEN")
    chat_id = _required_env("TELEGRAM_CHAT_ID")

    existing = next(
        (n for n in api.get_notifications() if n["name"] == TELEGRAM_NAME), None
    )
    if existing and not force:
        print(f"  ✓ Notification '{TELEGRAM_NAME}' already exists (id={existing['id']})")
        return existing["id"]

    if existing and force:
        print(f"  ↻ Deleting existing notification '{TELEGRAM_NAME}' for recreate")
        api.delete_notification(existing["id"])

    res = api.add_notification(
        name=TELEGRAM_NAME,
        type=NotificationType.TELEGRAM,
        isDefault=True,  # auto-attach to every new monitor
        applyExisting=False,
        telegramBotToken=bot_token,
        telegramChatID=chat_id,
    )
    nid = res["id"] if isinstance(res, dict) else res
    print(f"  ✓ Created notification '{TELEGRAM_NAME}' (id={nid})")
    return nid


def _ensure_monitor(
    api: UptimeKumaApi, spec: MonitorSpec, telegram_id: int, force: bool
) -> None:
    """Create/update one monitor by name."""
    existing = next(
        (m for m in api.get_monitors() if m["name"] == spec.name), None
    )
    if existing and not force:
        print(f"  ✓ Monitor '{spec.name}' already exists (id={existing['id']})")
        return
    if existing and force:
        print(f"  ↻ Deleting existing monitor '{spec.name}' for recreate")
        api.delete_monitor(existing["id"])

    kwargs: dict[str, Any] = dict(
        name=spec.name,
        type=spec.type,
        interval=spec.interval,
        retryInterval=spec.retry_interval,
        maxretries=spec.max_retries,
        timeout=spec.timeout,
        description=spec.description,
        notificationIDList=[telegram_id] if spec.notify_telegram else [],
    )

    # accepted_statuscodes only makes sense for HTTP-ish types.
    if spec.type in (MonitorType.HTTP, MonitorType.KEYWORD, MonitorType.JSON_QUERY):
        kwargs["accepted_statuscodes"] = spec.accepted_codes
        kwargs["expiryNotification"] = spec.expiry_notification

    kwargs.update(spec.extra)

    res = api.add_monitor(**kwargs)
    mid = res["monitorID"] if isinstance(res, dict) else res
    print(f"  ✓ Created monitor '{spec.name}' (id={mid}, type={spec.type.value})")


# ─── Main ───────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete + recreate existing entries instead of leaving them alone.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Connect, list what would change, then exit without writing.",
    )
    args = parser.parse_args()

    url = _required_env("KUMA_URL")
    user = _required_env("KUMA_USER")
    password = _required_env("KUMA_PASS")
    cookie = os.environ.get("KUMA_AUTHELIA_COOKIE", "")

    print(f"→ connecting to {url}")
    # `wait_events` shortens the per-call wait window. The default is 0.2s
    # which adds up over ~30 API calls; 0 lets the library finish as soon
    # as Kuma replies.
    headers = {}
    if cookie:
        headers["Cookie"] = f"authelia_session={cookie}"
    api = UptimeKumaApi(url, headers=headers, wait_events=0)

    try:
        api.login(user, password)
        print(f"  ✓ logged in as {user}")
    except Exception as exc:
        print(f"ERROR: Kuma login failed: {exc}", file=sys.stderr)
        api.disconnect()
        return 3

    if args.dry_run:
        print("\n--- DRY RUN: nothing will be written ---")
        existing_mons = {m["name"] for m in api.get_monitors()}
        existing_nots = {n["name"] for n in api.get_notifications()}
        print(f"  existing monitors:      {sorted(existing_mons) or '(none)'}")
        print(f"  existing notifications: {sorted(existing_nots) or '(none)'}")
        print(f"  would ensure: {TELEGRAM_NAME}")
        for spec in MONITORS:
            verb = "update" if spec.name in existing_mons else "create"
            print(f"  would {verb}: {spec.name} ({spec.type.value})")
        api.disconnect()
        return 0

    print("\n--- Notifications ---")
    telegram_id = _ensure_telegram(api, force=args.force)

    print("\n--- Monitors ---")
    for spec in MONITORS:
        try:
            _ensure_monitor(api, spec, telegram_id, force=args.force)
        except Exception as exc:
            print(f"  ✗ FAILED on '{spec.name}': {exc}", file=sys.stderr)

    api.disconnect()
    print("\n✓ done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
