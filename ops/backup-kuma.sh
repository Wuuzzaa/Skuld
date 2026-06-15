#!/usr/bin/env bash
# backup-kuma.sh
#
# Snapshot the Uptime Kuma SQLite + config volume into the same location
# the Postgres backups live, with a 7-day retention.
#
# Designed to be run by the same cron user that already owns
# /home/deploy/backups/postgres/. Add to deploy@'s crontab on prod:
#
#   30 3 * * * /opt/skuld/ops/backup-kuma.sh >> /home/deploy/backups/kuma.log 2>&1
#
# 30min after the Postgres dump (which runs at 03:00). Kuma volume is
# small (~5 MB), so we tar+gzip in one shot.

set -euo pipefail

KUMA_DIR="${KUMA_DIR:-/opt/skuld/uptime-kuma-data}"
DEST_DIR="${DEST_DIR:-/home/deploy/backups/kuma}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

if [[ ! -d "$KUMA_DIR" ]]; then
  echo "[$(date -Iseconds)] ERROR: KUMA_DIR not found: $KUMA_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"

stamp="$(date -u +%Y%m%d_%H%M%S)"
out="$DEST_DIR/kuma-${stamp}.tar.gz"

# -C so the archive paths are relative ("./db/kuma.db" not "/opt/skuld/...").
tar -czf "$out" -C "$(dirname "$KUMA_DIR")" "$(basename "$KUMA_DIR")"

# Sanity check: refuse to leave a 0-byte archive lying around.
if [[ ! -s "$out" ]]; then
  echo "[$(date -Iseconds)] ERROR: produced empty archive at $out" >&2
  rm -f "$out"
  exit 2
fi

# Retention: -mtime is whole-day rounded, +N matches strictly older than N days,
# which gives us "keep today + N previous days" = N+1 generations.
find "$DEST_DIR" -maxdepth 1 -name 'kuma-*.tar.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

echo "[$(date -Iseconds)] kuma backup OK: $out ($(stat -c%s "$out") bytes)"
