# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Arbeitsverzeichnis
WORKDIR /app

# System Dependencies (inkl. Cron für automatische Datensammlung + OpenSSH für VPN)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    cron \
    nano \
    openssh-client \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App Code kopieren
COPY . ./Skuld/

# Cronjob einrichten für 2x tägliche Datensammlung
COPY crontab /etc/cron.d/skuld-cron
COPY run_data_collection.sh /app/Skuld/run_data_collection.sh
RUN chmod 0644 /etc/cron.d/skuld-cron && \
    chmod +x /app/Skuld/run_data_collection.sh && \
    crontab /etc/cron.d/skuld-cron && \
    touch /var/log/cron.log

# Port für Streamlit
EXPOSE 8501

# Healthcheck (frontend only — backend overrides this with disable: true in compose)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Script for Backend (Cron)
COPY <<'BACKEND_SCRIPT' /app/start_backend.sh
#!/bin/bash
set -e
echo "Starting SKULD Backend..."

# Export environment variables for Cron
printenv | grep -E "TELEGRAM|PYTHON|MASSIVE|POSTGRES" > /app/env.sh
chmod 0644 /app/env.sh

# --- Wait for PostgreSQL to be ready ---
PG_HOST="${POSTGRES_HOST:-postgres}"
PG_PORT="${POSTGRES_PORT:-5432}"
echo "Waiting for PostgreSQL ($PG_HOST:$PG_PORT) to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0
while ! python3 -c "import socket; s=socket.create_connection(('$PG_HOST', int('$PG_PORT')), timeout=3); s.close()" 2>/dev/null; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
    echo "WARNING: PostgreSQL not reachable after $MAX_RETRIES attempts. Continuing anyway..."
    break
  fi
  echo "  Attempt $RETRY_COUNT/$MAX_RETRIES - PostgreSQL not ready, retrying in 3s..."
  sleep 3
done
echo "PostgreSQL connection check done"

# --- Run database migrations once on first container start ---
MIGRATION_FLAG="/app/.migrations_done"
if [ ! -f "$MIGRATION_FLAG" ]; then
  echo "First container start detected - running database migrations..."
  cd /app/Skuld && python main.py --mode only_run_migrations
  MIGRATION_EXIT=$?
  if [ $MIGRATION_EXIT -eq 0 ]; then
    echo "Database migrations completed successfully"
    touch "$MIGRATION_FLAG"
  else
    echo "Database migrations failed (exit code: $MIGRATION_EXIT)"
    exit $MIGRATION_EXIT
  fi
else
  echo "Migrations already applied (flag exists), skipping"
fi

# Start Cron Service
service cron start
echo "Cron service started"

# Keep container alive and show cron logs
touch /var/log/cron.log
exec tail -f /var/log/cron.log
BACKEND_SCRIPT
RUN chmod +x /app/start_backend.sh

# Start Script for Frontend (Streamlit)
COPY <<'FRONTEND_SCRIPT' /app/start_frontend.sh
#!/bin/bash
set -e
echo "Starting SKULD Frontend..."
exec streamlit run /app/Skuld/app.py --server.headless=true --server.enableCORS=false --server.port=8501 --server.address=0.0.0.0 --server.fileWatcherType=none
FRONTEND_SCRIPT
RUN chmod +x /app/start_frontend.sh

CMD ["/app/start_frontend.sh"]

