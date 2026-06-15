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

# Telegram (Ops-Channel preferred, falls back to trading chat). Same token
# pattern as backup_db.py / backup-authelia.sh — see audit notes about
# extracting these.
TG_TOKEN="${TELEGRAM_BOT_TOKEN:-8245443180:AAG0x1FfKfu1CYtj3CmiTb5FzDVlOB224dc}"
TG_CHAT="${TELEGRAM_OPS_CHAT_ID:-${TELEGRAM_CHAT_ID:--1003610692224}}"

notify_tg() {
    local text="$1"
    [[ -z "$TG_TOKEN" || "$TG_TOKEN" =~ ^REPLACE ]] && return 0
    curl -fsS --max-time 10 \
        --data-urlencode "chat_id=${TG_CHAT}" \
        --data-urlencode "parse_mode=HTML" \
        --data-urlencode "text=${text}" \
        "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
        > /dev/null 2>&1 || true
}

fail() {
    local msg="$1"
    echo "[$(date -Iseconds)] ERROR: $msg" >&2
    notify_tg "❌ <b>Kuma backup failed</b>%0A<code>${msg}</code>"
    exit 1
}

[[ -d "$KUMA_DIR" ]] || fail "KUMA_DIR not found: $KUMA_DIR"

mkdir -p "$DEST_DIR"

stamp="$(date -u +%Y%m%d_%H%M%S)"
out="$DEST_DIR/kuma-${stamp}.tar.gz"

# -C so the archive paths are relative ("./db/kuma.db" not "/opt/skuld/...").
tar -czf "$out" -C "$(dirname "$KUMA_DIR")" "$(basename "$KUMA_DIR")"

# Sanity check: refuse to leave a 0-byte archive lying around.
if [[ ! -s "$out" ]]; then
  rm -f "$out"
  fail "produced empty archive at $out"
fi

# Retention: -mtime is whole-day rounded, +N matches strictly older than N days,
# which gives us "keep today + N previous days" = N+1 generations.
find "$DEST_DIR" -maxdepth 1 -name 'kuma-*.tar.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

size="$(stat -c%s "$out")"
size_kb=$(( size / 1024 ))
echo "[$(date -Iseconds)] kuma backup OK: $out (${size} bytes / ${size_kb} KB)"
notify_tg "📦 <b>Kuma backup OK</b>%0AFile: <code>$(basename "$out")</code>%0ASize: ${size_kb} KB"
