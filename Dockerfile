FROM python:3.11-slim

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

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Script for Backend (Cron)
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting SKULD Backend..."\n\
\n\
# Export environment variables for Cron\n\
printenv | grep -E "TELEGRAM|PYTHON|MASSIVE|POSTGRES" > /app/env.sh\n\
chmod 0644 /app/env.sh\n\
\n\
# --- Wait for PostgreSQL to be ready ---\n\
echo "Waiting for PostgreSQL ($POSTGRES_HOST:$POSTGRES_PORT) to be ready..."\n\
MAX_RETRIES=30\n\
RETRY_COUNT=0\n\
while ! python -c "import socket; s=socket.create_connection((\x27${POSTGRES_HOST:-postgres}\x27, int(\x27${POSTGRES_PORT:-5432}\x27)), timeout=3); s.close()" 2>/dev/null; do\n\
  RETRY_COUNT=$((RETRY_COUNT + 1))\n\
  if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then\n\
    echo "✗ PostgreSQL not reachable after $MAX_RETRIES attempts. Continuing anyway..."\n\
    break\n\
  fi\n\
  echo "  Attempt $RETRY_COUNT/$MAX_RETRIES - PostgreSQL not ready, retrying in 3s..."\n\
  sleep 3\n\
done\n\
echo "✓ PostgreSQL connection check done"\n\
\n\
# --- Run database migrations once on first container start ---\n\
MIGRATION_FLAG="/app/.migrations_done"\n\
if [ ! -f "$MIGRATION_FLAG" ]; then\n\
  echo "First container start detected – running database migrations..."\n\
  cd /app/Skuld && python main.py --mode only_run_migrations\n\
  MIGRATION_EXIT=$?\n\
  if [ $MIGRATION_EXIT -eq 0 ]; then\n\
    echo "✓ Database migrations completed successfully"\n\
    touch "$MIGRATION_FLAG"\n\
  else\n\
    echo "✗ Database migrations failed (exit code: $MIGRATION_EXIT)"\n\
    exit $MIGRATION_EXIT\n\
  fi\n\
else\n\
  echo "✓ Migrations already applied (flag exists), skipping"\n\
fi\n\
\n\
# Start Cron Service\n\
service cron start\n\
echo "✓ Cron service started"\n\
\n\
# Initial data collection check\n\
if [ ! -f "/app/Skuld/db/financial_data.db" ]; then\n\
  echo "⚠ Database not found. Running initial data collection..."\n\
  cd /app/Skuld && python main.py --mode all || echo "Initial collection failed, will retry via cron"\n\
fi\n\
\n\
# Keep container alive and show cron logs\n\
touch /var/log/cron.log\n\
tail -f /var/log/cron.log' > /app/start_backend.sh && \
    chmod +x /app/start_backend.sh

# Start Script for Frontend (Streamlit)
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting SKULD Frontend..."\n\
\n\
exec streamlit run /app/Skuld/app.py --server.headless=true --server.enableCORS=false --server.port=8501 --server.address=0.0.0.0 --server.fileWatcherType=none' > /app/start_frontend.sh && \
    chmod +x /app/start_frontend.sh

CMD ["/app/start_frontend.sh"]

