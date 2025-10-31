# 🔄 Migration: Von Google Drive zu lokaler Persistenz

## Übersicht

**VORHER:**
- GitHub Actions lädt Daten 2x täglich hoch zu Google Drive
- Streamlit lädt Datenbank von Google Drive herunter
- Datenbank existiert nicht persistent auf dem Server

**NACHHER:**
- Docker Container mit Cronjob sammelt Daten 2x täglich
- Datenbank liegt persistent auf dem Server
- Kein Google Drive Upload/Download mehr nötig

## Änderungen die nötig sind

### 1. App.py - Google Drive Download entfernen

**Datei:** `app.py`

```python
# ENTFERNEN:
from src.google_drive_download import load_updated_database

@st.cache_data(ttl=1800, show_spinner="Checking for database updates...")
def ensure_database_available():
    """Downloads the database from Google Drive if needed."""
    if not use_local_data:
        load_updated_database()
ensure_database_available()

# ERSETZEN DURCH:
# Datenbank muss existieren (wird von Cronjob erstellt/aktualisiert)
if not PATH_DATABASE_FILE.exists():
    st.error("Database not found. Please wait for data collection to complete.")
    st.stop()
```

### 2. Main.py - Google Drive Upload entfernen

**Datei:** `main.py`

```python
# ENTFERNEN:
from src.google_drive_upload import upload_database

if upload_google_drive:
    logger.info("#" * 80)
    logger.info("Upload database to Google Drive")
    start = time.time()
    logger.info("#" * 80)
    upload_database()
    logger.info(f"Upload database to Google Drive - Done - Runtime: {int(time.time() - start)}s")

# VEREINFACHEN:
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run data collection pipeline")
    # --no-upload Argument ist nicht mehr nötig
    args = parser.parse_args()
    
    main()  # Einfach nur main() ohne Parameter
```

### 3. GitHub Actions Workflow deaktivieren/löschen

**Datei:** `.github/workflows/main.yml`

Entweder löschen oder deaktivieren, da der Cronjob jetzt im Docker Container läuft.

### 4. Optional: Google Drive Code komplett entfernen

**Dateien zum Löschen:**
- `src/google_drive_upload.py`
- `src/google_drive_download.py`

**Config Variablen entfernen aus `config.py`:**
```python
# Diese Zeilen entfernen:
PATH_ON_GOOGLE_DRIVE = "1ahLHST1IEUDf03TT3hEdbVm1r7rcxJcu"
FILENAME_GOOGLE_DRIVE = FILENAME_MERGED_DATAFRAME
PATH_FOR_SERVICE_ACCOUNT_FILE = ...
```

**Dependencies entfernen aus `requirements.txt`:**
```
# Diese entfernen:
google-auth>=2.23.0
google-api-python-client>=2.100.0
```

## Automatische Ausführung mit Cronjob im Docker

### Dockerfile erweitern

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System Dependencies mit Cron
RUN apt-get update && apt-get install -y \
    git \
    curl \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Python Dependencies
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# App Code kopieren
COPY Skuld/ ./Skuld/

# Cronjob einrichten
COPY crontab /etc/cron.d/skuld-cron
RUN chmod 0644 /etc/cron.d/skuld-cron && \
    crontab /etc/cron.d/skuld-cron && \
    touch /var/log/cron.log

# Streamlit Config
RUN mkdir -p ./Skuld/.streamlit /root/.streamlit
RUN echo "[server]" > /root/.streamlit/config.toml && \
    echo "headless = true" >> /root/.streamlit/config.toml && \
    echo "enableCORS = false" >> /root/.streamlit/config.toml && \
    echo "port = 8501" >> /root/.streamlit/config.toml && \
    echo "address = \"0.0.0.0\"" >> /root/.streamlit/config.toml

# Port für Streamlit
EXPOSE 8501

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Start Script erstellen
RUN echo '#!/bin/bash\n\
# Start Cron im Hintergrund\n\
cron\n\
echo "Cron started"\n\
# Erste Datensammlung beim Start (falls DB nicht existiert)\n\
if [ ! -f "/app/Skuld/db/financial_data.db" ]; then\n\
  echo "Initial data collection..."\n\
  cd /app/Skuld && python main.py\n\
fi\n\
# Streamlit starten\n\
exec python -m streamlit run Skuld/app.py' > /app/start.sh && \
    chmod +x /app/start.sh

CMD ["/app/start.sh"]
```

### Crontab Datei erstellen

**Neue Datei:** `crontab`

```cron
# 2x täglich: 10:00 und 16:00 CET (09:00 und 15:00 UTC)
# Format: Minute Hour Day Month Weekday Command
0 9 * * 1-5 cd /app/Skuld && /usr/local/bin/python main.py >> /var/log/cron.log 2>&1
0 15 * * 1-5 cd /app/Skuld && /usr/local/bin/python main.py >> /var/log/cron.log 2>&1

# Leere Zeile am Ende ist wichtig für Cron!

```

### docker-compose.yml anpassen

```yaml
version: '3.8'

services:
  skuld-app:
    build: .
    container_name: skuld-streamlit
    ports:
      - "8501:8501"
    volumes:
      # Datenbank persistent speichern (WICHTIG!)
      - ./Skuld/db:/app/Skuld/db
      # Logs persistent
      - ./Skuld/logs:/app/Skuld/logs
      # Cron logs
      - ./cron.log:/var/log/cron.log
      # Secrets (optional, wenn noch benötigt)
      - ${SECRETS_PATH:-./service_account.json}:/app/service_account.json:ro
    environment:
      - PYTHONUNBUFFERED=1
      - TZ=Europe/Berlin
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## Testing

### Lokal testen

```bash
# Container bauen und starten
docker-compose up -d --build

# Logs prüfen
docker-compose logs -f

# Cron Logs prüfen
docker-compose exec skuld-app cat /var/log/cron.log

# Manuell main.py ausführen (zum Testen)
docker-compose exec skuld-app python /app/Skuld/main.py

# Datenbank prüfen
docker-compose exec skuld-app ls -lh /app/Skuld/db/
```

### Cronjob manuell testen

```bash
# In Container shell gehen
docker-compose exec skuld-app bash

# Cron Status prüfen
service cron status

# Cronjobs anzeigen
crontab -l

# Manuell ausführen
cd /app/Skuld && python main.py
```

## Deployment auf Hetzner

### 1. Server vorbereiten

```bash
ssh root@YOUR_SERVER_IP

# Docker installieren (falls noch nicht geschehen)
apt update && apt install -y docker.io docker-compose git

# Projekt klonen
mkdir -p /opt/skuld && cd /opt/skuld
git clone https://github.com/Wuuzzaa/Skuld.git .
git checkout docker
```

### 2. Container starten

```bash
cd /opt/skuld

# Erste Datensammlung starten (initial)
docker-compose up -d --build

# Logs überwachen
docker-compose logs -f
```

### 3. Überwachen

```bash
# Streamlit Logs
docker-compose logs -f skuld-app

# Cron Logs
tail -f cron.log

# Datenbank Größe prüfen
ls -lh Skuld/db/financial_data.db

# Container Status
docker ps
```

## Vorteile der neuen Architektur

✅ **Keine Google Drive Abhängigkeit** - Einfacher und schneller
✅ **Persistente Datenbank** - Liegt auf dem Server
✅ **Automatische Updates** - Cronjob sammelt 2x täglich Daten
✅ **Keine GitHub Actions** - Spart GitHub Actions Minuten
✅ **Einfacheres Deployment** - Weniger moving parts
✅ **Bessere Performance** - Kein Download/Upload Overhead
✅ **Lokale Backups möglich** - `Skuld/db/` einfach sichern

## Backup Strategie

```bash
# Backup Script erstellen: /opt/skuld/backup.sh
#!/bin/bash
BACKUP_DIR="/opt/skuld-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp /opt/skuld/Skuld/db/financial_data.db $BACKUP_DIR/financial_data_${DATE}.db
# Alte Backups löschen (älter als 30 Tage)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete

# Cronjob für tägliches Backup
0 23 * * * /opt/skuld/backup.sh
```

## Troubleshooting

### Cronjob läuft nicht

```bash
# In Container prüfen
docker-compose exec skuld-app bash
service cron status
crontab -l

# Logs prüfen
tail -f /var/log/cron.log
```

### Datenbank wird nicht aktualisiert

```bash
# Manuell ausführen
docker-compose exec skuld-app python /app/Skuld/main.py

# Permissions prüfen
docker-compose exec skuld-app ls -la /app/Skuld/db/
```

### Container startet nicht

```bash
# Logs prüfen
docker-compose logs skuld-app

# Neustart
docker-compose down && docker-compose up -d --build
```
