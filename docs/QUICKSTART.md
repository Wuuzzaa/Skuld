# 🚀 Quick Start Guide - Docker Deployment

## Local Test (Windows)

```powershell
# 1. Navigate to project
cd C:\Python\SKULD\Skuld

# 2. Build and start container
docker-compose up -d --build

# 3. Monitor logs
docker-compose logs -f

# 4. Open Streamlit
# http://localhost:8501

# 5. Check cron logs (data collection)
type cron.log

# 6. Stop
docker-compose down
```

## Deploy to Hetzner Server

### 1. Prepare Server

```bash
# SSH connect
ssh root@YOUR_SERVER_IP

# Install Docker
apt update && apt install -y docker.io docker-compose git

# Create directory
mkdir -p /opt/skuld && cd /opt/skuld

# Clone repository
git clone https://github.com/Wuuzzaa/Skuld.git .
git checkout docker
```

### 2. Start Container

```bash
cd /opt/skuld

# Build and start
docker-compose up -d --build

# Check logs
docker-compose logs -f
```

### 3. Test Access

```
http://YOUR_SERVER_IP:8501
```

## Automatic Data Collection

The container automatically runs data collection **2x daily**:
- **10:00 CET** (09:00 UTC)
- **16:00 CET** (15:00 UTC)

Only on **weekdays** (Monday-Friday).

### Manually Trigger Data Collection

```bash
# Execute in container
docker-compose exec skuld-app python /app/Skuld/main.py
```

### Check Cron Status

```bash
# Show cron logs
tail -f cron.log

# Or in container
docker-compose exec skuld-app tail -f /var/log/cron.log

# Show cronjobs
docker-compose exec skuld-app crontab -l
```

## Important Commands

```bash
# Check status
docker ps

# View logs
docker-compose logs -f

# Restart container
docker-compose restart

# Stop container
docker-compose down

# Deploy updates
git pull
docker-compose up -d --build

# Check database
ls -lh db/financial_data.db

# Enter container shell
docker-compose exec skuld-app bash
```

## Persistent Data

All data is stored on the server:

```
/opt/skuld/
├── db/
│   └── financial_data.db  ← Persistent database
├── logs/
│   └── log.log             ← Streamlit logs
└── cron.log                ← Data collection logs
```

## Backup

```bash
# Backup database
cp /opt/skuld/db/financial_data.db /backup/skuld_$(date +%Y%m%d).db

# Or with docker-compose
docker-compose exec skuld-app cp /app/Skuld/db/financial_data.db /app/Skuld/db/backup_$(date +%Y%m%d).db
```

## Troubleshooting

### Container won't start

```bash
docker-compose logs skuld-app
docker-compose down && docker-compose up -d --build
```

### Database not found

```bash
# Create manually
docker-compose exec skuld-app python /app/Skuld/main.py
```

### Cronjob not running

```bash
# Check inside container
docker-compose exec skuld-app bash
service cron status
crontab -l
tail -f /var/log/cron.log
```

### Port already in use

```bash
# Edit docker-compose.yml:
ports:
  - "8502:8501"  # Use different port
```

## Production Setup with Nginx + SSL

```bash
# Install Nginx
apt install -y nginx certbot python3-certbot-nginx

# Create config
nano /etc/nginx/sites-available/skuld

# Content:
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

# Enable
ln -s /etc/nginx/sites-available/skuld /etc/nginx/sites-enabled/
nginx -t
systemlit reload nginx

# Get SSL certificate
certbot --nginx -d your-domain.com
```

## Monitoring

```bash
# Container resources
docker stats skuld-streamlit

# Disk space
df -h

# Rotate logs (automatic via Docker)
docker-compose logs --tail=1000

# Clean up old images
docker system prune -a
```

## Updates

```bash
cd /opt/skuld
git pull origin docker
docker-compose down
docker-compose up -d --build
```

## 🎯 That's it!

No secrets, no Google Drive, no GitHub Actions - everything runs **autonomously in the Docker container** with automatic data collection 2x daily! 🚀

```powershell
# 1. Zum Projekt wechseln
cd C:\Python\SKULD\Skuld

# 2. Container bauen und starten
docker-compose up -d --build

# 3. Logs überwachen
docker-compose logs -f

# 4. Streamlit öffnen
# http://localhost:8501

# 5. Cron Logs prüfen (Datensammlung)
type cron.log

# 6. Stoppen
docker-compose down
```

## Deployment auf Hetzner Server

### 1. Server vorbereiten

```bash
# SSH verbinden
ssh root@YOUR_SERVER_IP

# Docker installieren
apt update && apt install -y docker.io docker-compose git

# Verzeichnis erstellen
mkdir -p /opt/skuld && cd /opt/skuld

# Repository klonen
git clone https://github.com/Wuuzzaa/Skuld.git .
git checkout docker
```

### 2. Container starten

```bash
cd /opt/skuld

# Build und Start
docker-compose up -d --build

# Logs prüfen
docker-compose logs -f
```

### 3. Zugriff testen

```
http://YOUR_SERVER_IP:8501
```

## Automatische Datensammlung

Der Container führt **automatisch 2x täglich** die Datensammlung aus:
- **10:00 CET** (09:00 UTC)
- **16:00 CET** (15:00 UTC)

Nur an **Werktagen** (Montag-Freitag).

### Manuell Datensammlung starten

```bash
# Im Container ausführen
docker-compose exec skuld-app python /app/Skuld/main.py
```

### Cron Status prüfen

```bash
# Cron Logs anzeigen
tail -f cron.log

# Oder im Container
docker-compose exec skuld-app tail -f /var/log/cron.log

# Cronjobs anzeigen
docker-compose exec skuld-app crontab -l
```

## Wichtige Befehle

```bash
# Status prüfen
docker ps

# Logs anzeigen
docker-compose logs -f

# Container neu starten
docker-compose restart

# Container stoppen
docker-compose down

# Updates deployen
git pull
docker-compose up -d --build

# Datenbank prüfen
ls -lh db/financial_data.db

# In Container Shell
docker-compose exec skuld-app bash
```

## Persistente Daten

Alle Daten werden auf dem Server gespeichert:

```
/opt/skuld/
├── db/
│   └── financial_data.db  ← Persistente Datenbank
├── logs/
│   └── log.log             ← Streamlit Logs
└── cron.log                ← Datensammlung Logs
```

## Backup

```bash
# Datenbank sichern
cp /opt/skuld/db/financial_data.db /backup/skuld_$(date +%Y%m%d).db

# Oder mit docker-compose
docker-compose exec skuld-app cp /app/Skuld/db/financial_data.db /app/Skuld/db/backup_$(date +%Y%m%d).db
```

## Troubleshooting

### Container startet nicht

```bash
docker-compose logs skuld-app
docker-compose down && docker-compose up -d --build
```

### Datenbank nicht gefunden

```bash
# Manuell erstellen
docker-compose exec skuld-app python /app/Skuld/main.py
```

### Cronjob läuft nicht

```bash
# Im Container prüfen
docker-compose exec skuld-app bash
service cron status
crontab -l
tail -f /var/log/cron.log
```

### Port bereits belegt

```bash
# docker-compose.yml editieren:
ports:
  - "8502:8501"  # Anderen Port verwenden
```

## Produktiv-Setup mit Nginx + SSL

```bash
# Nginx installieren
apt install -y nginx certbot python3-certbot-nginx

# Config erstellen
nano /etc/nginx/sites-available/skuld

# Inhalt:
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}

# Aktivieren
ln -s /etc/nginx/sites-available/skuld /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# SSL Zertifikat
certbot --nginx -d your-domain.com
```

## Monitoring

```bash
# Container Ressourcen
docker stats skuld-streamlit

# Disk Space
df -h

# Logs rotieren (automatisch durch Docker)
docker-compose logs --tail=1000

# Alte Images aufräumen
docker system prune -a
```

## Updates

```bash
cd /opt/skuld
git pull origin docker
docker-compose down
docker-compose up -d --build
```

## 🎯 Das war's!

Keine Secrets, keine Google Drive, keine GitHub Actions - alles läuft **selbstständig im Docker Container** mit automatischer Datensammlung 2x täglich! 🚀
