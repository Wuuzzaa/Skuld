#!/bin/bash
# Wrapper script for cron: prevents multiple instances of main.py

# Load environment variables (Telegram Token etc.)
if [ -f /app/env.sh ]; then
    set -a
    . /app/env.sh
    set +a
fi

# Parameter für den Modus (z. B. option_data, saturday_night, marked_start_mid_end, stock_data_daily)
MODE="$1"

# Modus-spezifische Lockfile, Logfile und Memory-Monitor-Datei
LOCKFILE="/tmp/skuld_data_collection_${MODE}.lock"
LOGFILE="/var/log/cron_${MODE}.log"
MONITOR_LOG="/var/log/memory_monitor_${MODE}.csv"

# Check if already running
if [ -f "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$(date): Data collection (${MODE}) already running (PID: $PID). Skipping." >> "$LOGFILE"
        exit 0
    else
        echo "$(date): Stale lockfile found for ${MODE}. Removing." >> "$LOGFILE"
        rm -f "$LOCKFILE"
    fi
fi

# Create lockfile with current PID
echo $$ > "$LOCKFILE"

# Start Memory Monitor
echo "Timestamp,RSS_MB" > "$MONITOR_LOG"
(
    while true; do
        # RSS in MB (Sum of all python processes)
        RSS=$(ps -e -o rss,comm | grep python | awk '{s+=$1} END {print int(s/1024)}')
        echo "$(date '+%Y-%m-%d %H:%M:%S'),${RSS:-0}" >> "$MONITOR_LOG"
        sleep 5
    done
) &
MONITOR_PID=$!

# Run data collection with timeout and reduced CPU/IO priority
# nice -n 10: lower CPU scheduling priority (default=0, max=19)
# ionice -c 2 -n 6: best-effort IO class with lower priority (0=highest, 7=lowest)
cd /app/Skuld
echo "$(date): Starting data collection (${MODE})..." >> "$LOGFILE"
timeout 18000 nice -n 10 ionice -c 2 -n 6 /usr/local/bin/python main.py --mode "$MODE" >> "$LOGFILE" 2>&1
EXIT_CODE=$?

# Stop Memory Monitor
kill $MONITOR_PID 2>/dev/null

# Remove lockfile
rm -f "$LOCKFILE"

# Handle exit codes
if [ $EXIT_CODE -eq 124 ]; then
    echo "$(date): Data collection (${MODE}) timed out after 2 hours" >> "$LOGFILE"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Timeout" "Data collection (${MODE}) timed out after 2 hours." >> "$LOGFILE" 2>&1
elif [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Data collection (${MODE}) completed successfully" >> "$LOGFILE"
    # Success alert handled by main.py
elif [ $EXIT_CODE -eq 137 ]; then
    echo "$(date): Data collection (${MODE}) failed with OUT OF MEMORY (Exit Code 137)" >> "$LOGFILE"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Out of Memory" "The data collection process (${MODE}) was killed (Exit Code 137). Please check the logs and memory usage." >> "$LOGFILE" 2>&1
else
    echo "$(date): Data collection (${MODE}) failed with exit code $EXIT_CODE" >> "$LOGFILE"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Failure" "Data collection (${MODE}) failed with exit code $EXIT_CODE. Please check the logs." >> "$LOGFILE" 2>&1
fi

exit 0
