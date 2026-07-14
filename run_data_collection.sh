#!/bin/bash
# Wrapper script for cron: prevents multiple instances of main.py

# Load environment variables (Telegram Token etc.)
if [ -f /app/env.sh ]; then
    set -a
    . /app/env.sh
    set +a
fi

# Parameter für den Modus (z. B. option_data, saturday_night, market_start_mid_end, stock_data_daily)
MODE="$1"

# ---------------------------------------------------------------------------
# Central job-status log: one JSONL line per finished job.
# Written into logs/_status/YYYY-MM-DD.jsonl so the existing 14-day log
# cleanup cron (find /app/Skuld/logs -mtime +14 -delete) rotates it for free.
# The admin "Job Status" tab visualises this file — no need to read each log.
# Captures crashes/OOM/timeout too, because this runs after the wrapper exit.
# write_status <status> <exit_code> <duration_s> <note>
# ---------------------------------------------------------------------------
write_status() {
    local status="$1" ec="$2" dur="$3" note="$4"
    local status_dir="/app/Skuld/logs/_status"
    local status_file="${status_dir}/$(date -u +%F).jsonl"
    mkdir -p "$status_dir"
    # Escape backslashes and double quotes in the free-text note for valid JSON.
    note="${note//\\/\\\\}"
    note="${note//\"/\\\"}"
    printf '{"ts":"%s","mode":"%s","status":"%s","exit_code":%s,"duration_s":%s,"note":"%s"}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$MODE" "$status" "${ec:-0}" "${dur:-0}" "$note" \
        >> "$status_file"
}

# Modus-spezifische Lockfile, Logfile und Memory-Monitor-Datei
LOCKFILE="/tmp/skuld_data_collection_${MODE}.lock"
LOGFILE="/var/log/cron_${MODE}.log"
MONITOR_LOG="/var/log/memory_monitor_${MODE}.csv"

# Check if already running
if [ -f "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$(date): Data collection (${MODE}) already running (PID: $PID). Skipping." >> "$LOGFILE"
        write_status "SKIPPED" 0 0 "already running (PID ${PID})"
        exit 0
    else
        echo "$(date): Stale lockfile found for ${MODE}. Removing." >> "$LOGFILE"
        rm -f "$LOCKFILE"
    fi
fi

# Create lockfile with current PID
echo $$ > "$LOCKFILE"

# Start Memory Monitor (lightweight, 60s interval — Python has its own detailed monitor)
echo "Timestamp,RSS_MB" > "$MONITOR_LOG"
(
    while true; do
        RSS=$(ps -e -o rss,comm | grep python | awk '{s+=$1} END {print int(s/1024)}')
        echo "$(date '+%Y-%m-%d %H:%M:%S'),${RSS:-0}" >> "$MONITOR_LOG"
        sleep 60
    done
) &
MONITOR_PID=$!

# Run data collection with timeout and reduced CPU/IO priority
# nice -n 10: lower CPU scheduling priority (default=0, max=19)
# ionice -c 2 -n 6: best-effort IO class with lower priority (0=highest, 7=lowest)
# Historical modes get 24h timeout; regular modes get 5h
case "$MODE" in
    historical_*) TIMEOUT=86400 ;;
    all|saturday_night) TIMEOUT=21600 ;;
    *) TIMEOUT=18000 ;;
esac

cd /app/Skuld
echo "$(date): Starting data collection (${MODE}) [timeout=${TIMEOUT}s]..." >> "$LOGFILE"
START_TS=$(date +%s)
timeout $TIMEOUT nice -n 10 ionice -c 2 -n 6 /usr/local/bin/python main.py --mode "$MODE" >> "$LOGFILE" 2>&1
EXIT_CODE=$?
DURATION=$(( $(date +%s) - START_TS ))

# Stop Memory Monitor
kill $MONITOR_PID 2>/dev/null

# Remove lockfile
rm -f "$LOCKFILE"

# Handle exit codes
if [ $EXIT_CODE -eq 124 ]; then
    TIMEOUT_H=$((TIMEOUT / 3600))
    echo "$(date): Data collection (${MODE}) timed out after ${TIMEOUT_H}h" >> "$LOGFILE"
    write_status "TIMEOUT" "$EXIT_CODE" "$DURATION" "timed out after ${TIMEOUT_H}h"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Timeout" "Data collection (${MODE}) timed out after ${TIMEOUT_H}h." >> "$LOGFILE" 2>&1
elif [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Data collection (${MODE}) completed successfully" >> "$LOGFILE"
    write_status "OK" "$EXIT_CODE" "$DURATION" ""
    # Success alert handled by main.py
elif [ $EXIT_CODE -eq 137 ]; then
    echo "$(date): Data collection (${MODE}) failed with OUT OF MEMORY (Exit Code 137)" >> "$LOGFILE"
    write_status "OOM" "$EXIT_CODE" "$DURATION" "killed out of memory (137)"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Out of Memory" "The data collection process (${MODE}) was killed (Exit Code 137). Please check the logs and memory usage." >> "$LOGFILE" 2>&1
else
    echo "$(date): Data collection (${MODE}) failed with exit code $EXIT_CODE" >> "$LOGFILE"
    write_status "FAIL" "$EXIT_CODE" "$DURATION" "failed with exit code ${EXIT_CODE}"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Failure" "Data collection (${MODE}) failed with exit code $EXIT_CODE. Please check the logs." >> "$LOGFILE" 2>&1
fi

exit 0
