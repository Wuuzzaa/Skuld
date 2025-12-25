#!/bin/bash
# Test script to simulate OOM and verify Telegram alert

LOGFILE="/var/log/cron.log"

echo "$(date): Starting OOM simulation..." >> "$LOGFILE"

# Run the memory consumer
# We expect this to be killed by OOM killer (Exit Code 137)
/usr/local/bin/python src/simulate_oom.py >> "$LOGFILE" 2>&1
EXIT_CODE=$?

echo "Process finished with Exit Code: $EXIT_CODE"

if [ $EXIT_CODE -eq 137 ]; then
    echo "$(date): OOM Simulation successful (Exit Code 137)" >> "$LOGFILE"
    # Send Telegram alert
    /usr/local/bin/python src/send_alert.py "SKULD TEST: OOM Alert" "This is a TEST. The OOM simulation was killed (Exit Code 137). Alert system is working." >> "$LOGFILE" 2>&1
else
    echo "$(date): OOM Simulation failed to trigger 137. Got: $EXIT_CODE" >> "$LOGFILE"
fi
