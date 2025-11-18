#!/bin/bash
# Wrapper script for cron: prevents multiple instances of main.py

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

# Run data collection with timeout
cd /app/Skuld
echo "$(date): Starting data collection..." >> "$LOGFILE"
timeout 7200 /usr/local/bin/python main.py >> "$LOGFILE" 2>&1
EXIT_CODE=$?

# Remove lockfile
rm -f "$LOCKFILE"

if [ $EXIT_CODE -eq 124 ]; then
    echo "$(date): Data collection timed out after 2 hours" >> "$LOGFILE"
elif [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Data collection completed successfully" >> "$LOGFILE"
else
    echo "$(date): Data collection failed with exit code $EXIT_CODE" >> "$LOGFILE"
fi

exit 0
