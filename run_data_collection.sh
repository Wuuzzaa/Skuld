#!/bin/bash
# Wrapper script for cron: prevents multiple instances of main.py

# Load environment variables (Telegram Token etc.)
if [ -f /app/env.sh ]; then
    set -a
    . /app/env.sh
    set +a
fi

LOCKFILE="/tmp/skuld_data_collection.lock"
LOGFILE="/var/log/cron.log"

# Check if already running
if [ -f "$LOCKFILE" ]; then
    PID=$(cat "$LOCKFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "$(date): Data collection already running (PID: $PID). Skipping." >> "$LOGFILE"
        exit 0
    else
        echo "$(date): Stale lockfile found. Removing." >> "$LOGFILE"
        rm -f "$LOCKFILE"
    fi
fi

# Create lockfile with current PID
echo $$ > "$LOCKFILE"

# Start Memory Monitor
MONITOR_LOG="/var/log/memory_monitor.csv"
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

# Run data collection with timeout
cd /app/Skuld
echo "$(date): Starting data collection..." >> "$LOGFILE"
timeout 7200 /usr/local/bin/python main.py --no-upload >> "$LOGFILE" 2>&1
EXIT_CODE=$?

# Stop Memory Monitor
kill $MONITOR_PID 2>/dev/null

# Remove lockfile
rm -f "$LOCKFILE"

if [ $EXIT_CODE -eq 124 ]; then
    echo "$(date): Data collection timed out after 2 hours" >> "$LOGFILE"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Timeout" "Data collection timed out after 2 hours." >> "$LOGFILE" 2>&1
elif [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Data collection completed successfully" >> "$LOGFILE"
    # Send Success Telegram alert
    /usr/local/bin/python src/send_alert.py "SKULD Info: Success" "Data collection completed successfully." >> "$LOGFILE" 2>&1
elif [ $EXIT_CODE -eq 137 ]; then
    echo "$(date): Data collection failed with OUT OF MEMORY (Exit Code 137)" >> "$LOGFILE"
    # Send Telegram alert
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Out of Memory" "The data collection process was killed (Exit Code 137). Please check the logs and memory usage." >> "$LOGFILE" 2>&1
else
    echo "$(date): Data collection failed with exit code $EXIT_CODE" >> "$LOGFILE"
    /usr/local/bin/python src/send_alert.py "SKULD Alert: Failure" "Data collection failed with exit code $EXIT_CODE. Please check the logs." >> "$LOGFILE" 2>&1
fi

exit 0
