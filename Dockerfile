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
printenv | grep -E "TELEGRAM|PYTHON|MASSIVE" > /app/env.sh\n\
chmod 0644 /app/env.sh\n\
\n\
# Start Cron Service\n\
service cron start\n\
echo "✓ Cron service started"\n\
\n\
# Initial data collection check\n\
if [ ! -f "/app/Skuld/db/financial_data.db" ]; then\n\
  echo "⚠ Database not found. Running initial data collection..."\n\
  cd /app/Skuld && python main.py || echo "Initial collection failed, will retry via cron"\n\
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

