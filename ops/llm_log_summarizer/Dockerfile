FROM python:3.11-slim

# Install cron and curl
RUN apt-get update && apt-get install -y cron curl && rm -rf /var/lib/apt/lists/*

# Install python dependencies
RUN pip install --no-cache-dir requests

WORKDIR /app

# Copy scripts
COPY summarize_logs.py /app/summarize_logs.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# We use an entrypoint script to setup the cronjob at runtime so it can access env vars
ENTRYPOINT ["/app/entrypoint.sh"]
