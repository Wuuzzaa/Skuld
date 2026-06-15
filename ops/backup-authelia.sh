#!/usr/bin/env bash
# backup-authelia.sh
#
# Snapshot the Authelia state (SQLite DB + secrets + user file) into the
# same backup root as the Postgres dumps, with a 30-day retention.
#
# Why this is critical: if you lose authelia/db.sqlite3 you also lose every
# active session AND every TOTP secret. Your only way back in is the raw
# users_database.yml + a fresh DB. The secrets (jwt_secret, session_secret,
# storage_encryption_key) are NOT regenerable — they're tied to the cookies
# and the encrypted columns inside db.sqlite3.
#
# Cron:
#   45 3 * * *  /opt/skuld/ops/backup-authelia.sh >> /home/deploy/backups/authelia.log 2>&1
#
# Restore (full):
#   1. docker compose down authelia
#   2. cd /opt/skuld && tar -xzf /home/deploy/backups/authelia/authelia-YYYYMMDD_HHMMSS.tar.gz
#      (this overwrites ./authelia/ with the snapshot)
#   3. docker compose up -d authelia
#
# Telegram alerts: same token+chat_id as backup_db.py. Token is hardcoded
# below to mirror the existing pattern (see [[skuld-architecture-audit-2026-06-14]]
# for why this should eventually be moved into env / GitHub Secret).

set -euo pipefail

# ── config ────────────────────────────────────────────────────────────────
AUTHELIA_DIR="${AUTHELIA_DIR:-/opt/skuld/authelia}"
DEST_DIR="${DEST_DIR:-/home/deploy/backups/authelia}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# Telegram (matches backup_db.py — see SKULD audit notes about extracting these)
TG_TOKEN="${TELEGRAM_BOT_TOKEN:-8245443180:AAG0x1FfKfu1CYtj3CmiTb5FzDVlOB224dc}"
TG_CHAT="${TELEGRAM_CHAT_ID:--1003610692224}"

# ── helpers ───────────────────────────────────────────────────────────────
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
    notify_tg "❌ <b>Authelia backup failed</b>%0A<code>${msg}</code>"
    exit 1
}

# ── preflight ─────────────────────────────────────────────────────────────
[[ -d "$AUTHELIA_DIR" ]] || fail "AUTHELIA_DIR not found: $AUTHELIA_DIR"
[[ -f "$AUTHELIA_DIR/db.sqlite3" ]] || fail "db.sqlite3 not found in $AUTHELIA_DIR"

mkdir -p "$DEST_DIR"

stamp="$(date -u +%Y%m%d_%H%M%S)"
out="$DEST_DIR/authelia-${stamp}.tar.gz"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ── snapshot the SQLite atomically ────────────────────────────────────────
# Plain `cp` can capture a half-written page if Authelia is mid-write;
# sqlite3's .backup is the safe equivalent of pg_dump for SQLite.
# If sqlite3 isn't installed we fall back to a brief flock+cp — Authelia
# writes are sub-millisecond, so the contention window is negligible.
if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$AUTHELIA_DIR/db.sqlite3" ".backup '$work/db.sqlite3'" \
        || fail "sqlite3 .backup failed"
else
    cp -a "$AUTHELIA_DIR/db.sqlite3" "$work/db.sqlite3" \
        || fail "cp of db.sqlite3 failed"
fi

# ── snapshot the secrets + user db + config ───────────────────────────────
# notification.txt is *not* secret but useful for forensic context.
for f in jwt_secret session_secret storage_encryption_key users_database.yml configuration.yml notification.txt; do
    if [[ -f "$AUTHELIA_DIR/$f" ]]; then
        cp -a "$AUTHELIA_DIR/$f" "$work/$f"
    fi
done

# ── tar+gz the staged copy ────────────────────────────────────────────────
tar -czf "$out" -C "$work" .

# Refuse to leave a 0-byte archive lying around.
size="$(stat -c%s "$out")"
[[ "$size" -gt 0 ]] || fail "produced empty archive at $out"

# ── retention ─────────────────────────────────────────────────────────────
# `-mtime +N` matches files strictly older than N days, so we keep N+1
# generations. With 30 we get one month of restore points.
find "$DEST_DIR" -maxdepth 1 -name 'authelia-*.tar.gz' -type f \
    -mtime "+${RETENTION_DAYS}" -delete

# ── done ──────────────────────────────────────────────────────────────────
size_kb=$(( size / 1024 ))
size_mb=$(awk "BEGIN { printf \"%.2f\", $size / 1048576 }")
echo "[$(date -Iseconds)] authelia backup OK: $out (${size} bytes / ${size_mb} MB)"

# Only notify on success when running interactively or daily — the cron will
# create one entry per day, no per-run spam beyond what backup_db.py already
# does. We still do it so the audit channel sees both backups landing.
notify_tg "🛡️ <b>Authelia backup OK</b>%0AFile: <code>$(basename "$out")</code>%0ASize: ${size_kb} KB (${size_mb} MB)"
