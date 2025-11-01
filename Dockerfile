FROM python:3.11-slim

# Arbeitsverzeichnis
WORKDIR /app

# System Dependencies (inkl. Cron für automatische Datensammlung)
RUN apt-get update && apt-get install -y \
    git \
    curl \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App Code kopieren
COPY . ./Skuld/

# Cronjob einrichten für 2x tägliche Datensammlung
COPY crontab /etc/cron.d/skuld-cron
RUN chmod 0644 /etc/cron.d/skuld-cron && \
    crontab /etc/cron.d/skuld-cron && \
    touch /var/log/cron.log

# Port für Streamlit
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Script für Cron + Streamlit
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting SKULD container..."\n\
\n\
# Start Cron Service\n\
service cron start\n\
echo "✓ Cron service started (2x daily data collection: 10:00 and 16:00 CET)"\n\
\n\
# Initial data collection if database does not exist\n\
if [ ! -f "/app/Skuld/db/financial_data.db" ]; then\n\
  echo "⚠ Database not found. Running initial data collection..."\n\
  cd /app/Skuld && python main.py || echo "Initial collection failed, will retry via cron"\n\
else\n\
  echo "✓ Database exists"\n\
fi\n\
\n\
# Start Streamlit\n\
echo "Starting Streamlit on port 8501..."\n\
exec streamlit run /app/Skuld/app.py --server.headless=true --server.enableCORS=false --server.port=8501 --server.address=0.0.0.0 --server.fileWatcherType=none' > /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]

