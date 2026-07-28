#!/bin/bash
# Daily watchlist backup - keeps last 7 days only.
#
# Alerts via Telegram if the backup copy fails. Previously this failed
# SILENTLY with exit 0: 'find -delete' was the last command, so a failed
# 'cp' was masked. On IONOS (2026-07-22) a root-owned backups dir hid a
# Permission-denied for days without any alert. Now every failure is loud.

SRC=/opt/skuld/data/watchlist.xlsx
BACKUP_DIR=/opt/skuld/data/backups
DATE=$(date +%Y-%m-%d)
ENVF=/opt/skuld/.env

# --- Telegram alert helper ---
# Reads secrets with grep|cut (NOT '. .env'): SKULD_VERSION in .env contains
# parens/spaces and breaks 'source'. Same pattern as monitor.sh/disk_report.sh.
send_alert() {
    local msg="$1"
    local token chat host
    token="$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENVF" 2>/dev/null | cut -d= -f2-)"
    chat="$(grep -E '^TELEGRAM_CHAT_ID=' "$ENVF" 2>/dev/null | cut -d= -f2-)"
    host="$(hostname)"
    [ -z "$token" ] || [ -z "$chat" ] && return 0
    /usr/bin/curl -s -X POST "https://api.telegram.org/bot$token/sendMessage" \
        -d "chat_id=$chat" \
        -d "text=⚠️ *WATCHLIST-BACKUP FEHLGESCHLAGEN* ($host)%0A%0A$msg" \
        -d "parse_mode=Markdown" > /dev/null
}

# No source file yet (scanner hasn't created it) = not an error.
[ ! -f "$SRC" ] && exit 0

if ! mkdir -p "$BACKUP_DIR" 2>/dev/null; then
    send_alert "mkdir '$BACKUP_DIR' fehlgeschlagen (Rechte?)."
    exit 1
fi

if ! cp "$SRC" "$BACKUP_DIR/watchlist_${DATE}.xlsx" 2>/dev/null; then
    send_alert "cp nach '$BACKUP_DIR' fehlgeschlagen — vermutlich Ordner-Rechte (owner != deploy?)."
    exit 1
fi

# Remove backups older than 7 days
find "$BACKUP_DIR" -name 'watchlist_*.xlsx' -mtime +7 -delete

exit 0
