#!/bin/bash

# Export all environment variables to a file so cron can use them
env > /etc/environment

# Setup the cron job
# Run every day at 21:00 (or adapt timezone as needed)
echo "0 21 * * * root . /etc/environment; /usr/local/bin/python /app/summarize_logs.py >> /var/log/cron.log 2>&1" > /etc/cron.d/summarize_cron
chmod 0644 /etc/cron.d/summarize_cron
crontab /etc/cron.d/summarize_cron

# Start cron daemon
cron

# Display logs to keep container alive and observable
echo "Log Summarizer started. Cronjob configured to run daily at 21:00."
echo "Running an initial summary right now..."
/usr/local/bin/python /app/summarize_logs.py

tail -f /var/log/cron.log
