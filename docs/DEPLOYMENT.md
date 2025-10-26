# 🚀 SKULD Docker Deployment Guide

## Overview

SKULD runs completely in Docker with:
- ✅ **Persistent local database** (no Google Drive)
- ✅ **Automatic data collection** 2x daily via cronjob
- ✅ **Streamlit web interface** on port 8501
- ✅ **No external secrets** required

---

## 1. Local Testing (Windows/Linux/Mac)

### Prerequisites
- Docker & Docker Compose installed
- Git installed

### Quick Start

```bash
# Clone repository
git clone https://github.com/Wuuzzaa/Skuld.git
cd Skuld
git checkout docker

# Start container
docker-compose up -d --build

# Monitor logs
docker-compose logs -f
```

### Access
Open browser: **http://localhost:8501**

### Useful Commands

```bash
# Container status
docker ps

# View logs
docker-compose logs -f

# Cron logs (data collection)
tail -f cron.log

# Restart container
docker-compose restart

# Stop container
docker-compose down

# Manually trigger data collection
docker-compose exec skuld-app python /app/Skuld/main.py
```

---

## 2. Production Deployment on Hetzner

### Server Preparation (one-time)

```bash
# 1. SSH to server
ssh root@YOUR_SERVER_IP

# 2. Update system
apt update && apt upgrade -y

# 3. Install Docker
apt install -y docker.io docker-compose git curl

# 4. Start Docker
systemctl start docker
systemctl enable docker

# 5. Configure firewall
ufw allow 22/tcp      # SSH
ufw allow 8501/tcp    # Streamlit
ufw enable
```

### Deploy Project

```bash
# 1. Create project directory
mkdir -p /opt/skuld
cd /opt/skuld

# 2. Clone repository
git clone https://github.com/Wuuzzaa/Skuld.git .
git checkout docker

# 3. Create persistent directories
mkdir -p db logs

# 4. Start container
docker-compose up -d --build

# 5. Check logs
docker-compose logs -f
```

### Test Access
Browser: **http://YOUR_SERVER_IP:8501**

---

## 3. Automatic Data Collection

### Schedule (Cronjob)

Container automatically collects data:
- **10:00 CET** (09:00 UTC) - Morning
- **16:00 CET** (15:00 UTC) - Afternoon
- **Weekdays only** (Monday-Friday)

### Check Cronjob

```bash
# Show cronjobs
docker-compose exec skuld-app crontab -l

# Cron service status
docker-compose exec skuld-app service cron status

# Live cron logs
tail -f cron.log
```

### Manual Execution

```bash
# Start data collection immediately
docker-compose exec skuld-app python /app/Skuld/main.py

# With logs
docker-compose exec skuld-app bash -c "cd /app/Skuld && python main.py"
```

---

## 4. Persistent Data

All data is stored on the host:

```
/opt/skuld/
├── db/
│   └── financial_data.db    # SQLite database (approx. 50-200 MB)
├── logs/
│   └── log.log               # Streamlit & app logs
└── cron.log                  # Data collection logs
```

### Database Backup

```bash
# Manual backup
cp /opt/skuld/db/financial_data.db \
   /opt/skuld/backups/financial_data_$(date +%Y%m%d).db

# Create automated backup script
cat > /opt/skuld/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/skuld-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp /opt/skuld/db/financial_data.db $BACKUP_DIR/financial_data_${DATE}.db
# Delete old backups (older than 30 days)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
echo "Backup completed: financial_data_${DATE}.db"
EOF

chmod +x /opt/skuld/backup.sh

# Add cronjob for daily backup (11:00 PM)
crontab -e
# Add this line:
0 23 * * * /opt/skuld/backup.sh >> /opt/skuld/backup.log 2>&1
```

---

## 5. Deploy Updates

```bash
cd /opt/skuld

# 1. Update code
git pull origin docker

# 2. Rebuild and restart container
docker-compose down
docker-compose up -d --build

# 3. Check logs
docker-compose logs -f

# 4. Clean up old images
docker system prune -a -f
```

---

## 6. Monitoring & Maintenance

### Monitor Container

```bash
# Container status
docker ps

# Resource usage
docker stats skuld-streamlit

# Check disk space
df -h
du -sh /opt/skuld/db/

# Check log size
ls -lh /opt/skuld/logs/
ls -lh /opt/skuld/cron.log
```

### Log Rotation

Docker rotates logs automatically, but for cron.log:

```bash
# Configure log rotation
cat > /etc/logrotate.d/skuld << 'EOF'
/opt/skuld/cron.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
EOF
```

---

## 7. Production Setup with SSL (Optional)

### Nginx Reverse Proxy

```bash
# Install Nginx
apt install -y nginx certbot python3-certbot-nginx

# Create Nginx config
cat > /etc/nginx/sites-available/skuld << 'EOF'
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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable
ln -s /etc/nginx/sites-available/skuld /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Update firewall
ufw allow 80/tcp
ufw allow 443/tcp

# Get free SSL certificate
certbot --nginx -d your-domain.com
```

### Adjust docker-compose.yml

```yaml
# Make port internal only
ports:
  - "127.0.0.1:8501:8501"  # localhost only, not public
```

Then: `docker-compose up -d`

---

## 8. Troubleshooting

### Container won't start

```bash
# Detailed logs
docker-compose logs skuld-app

# Container status
docker ps -a

# Force restart
docker-compose down -v
docker-compose up -d --build
```

### Database not found

```bash
# Does database exist?
ls -lh /opt/skuld/db/

# Check permissions
docker-compose exec skuld-app ls -la /app/Skuld/db/

# Create manually
docker-compose exec skuld-app python /app/Skuld/main.py
```

### Cronjob not running

```bash
# Check inside container
docker-compose exec skuld-app bash

# Cron status
service cron status

# Show cronjobs
crontab -l

# Check logs
tail -f /var/log/cron.log
exit

# On host
tail -f /opt/skuld/cron.log
```

### Streamlit not loading

```bash
# Is container running?
docker ps | grep skuld

# Is port accessible?
curl http://localhost:8501

# Firewall?
ufw status

# Check logs
docker-compose logs -f
```

### Disk space full

```bash
# Delete old Docker images
docker system prune -a -f

# Delete old logs
truncate -s 0 /opt/skuld/logs/log.log
truncate -s 0 /opt/skuld/cron.log

# Delete old backups
find /opt/skuld-backups -name "*.db" -mtime +30 -delete
```

---

## 9. Security

### Best Practices

```bash
# SSH key-only authentication
nano /etc/ssh/sshd_config
# PasswordAuthentication no
systemctl restart sshd

# Minimize firewall rules
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Automatic updates
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# Fail2ban for SSH protection
apt install -y fail2ban
systemctl enable fail2ban
```

---

## 10. Summary

### What you need:
✅ Hetzner server (or any Linux server)  
✅ Docker & Docker Compose  
✅ Git  
✅ Port 8501 open (or Nginx for SSL)

### What you DON'T need:
❌ Google Drive API  
❌ Service account secrets  
❌ GitHub Actions  
❌ External database  

### Deploy in 3 commands:
```bash
git clone https://github.com/Wuuzzaa/Skuld.git && cd Skuld
git checkout docker
docker-compose up -d --build
```

**🎉 Done! The app runs and automatically collects data 2x daily!**
- ✅ **Persistente lokale Datenbank** (keine Google Drive)
- ✅ **Automatische Datensammlung** 2x täglich per Cronjob
- ✅ **Streamlit Web-Interface** auf Port 8501
- ✅ **Keine externen Secrets** benötigt

---

## 1. Lokaler Test (Windows/Linux/Mac)

### Prerequisites
- Docker & Docker Compose installiert
- Git installiert

### Schnellstart

```bash
# Repository klonen
git clone https://github.com/Wuuzzaa/Skuld.git
cd Skuld
git checkout docker

# Container starten
docker-compose up -d --build

# Logs überwachen
docker-compose logs -f
```

### Zugriff
Öffne Browser: **http://localhost:8501**

### Wichtige Befehle

```bash
# Container Status
docker ps

# Logs anzeigen
docker-compose logs -f

# Cron Logs (Datensammlung)
tail -f cron.log

# Container neu starten
docker-compose restart

# Container stoppen
docker-compose down

# Manuell Datensammlung starten
docker-compose exec skuld-app python /app/Skuld/main.py
```

---

## 2. Production Deployment auf Hetzner

### Server Vorbereitung (einmalig)

```bash
# 1. SSH zum Server
ssh root@YOUR_SERVER_IP

# 2. System aktualisieren
apt update && apt upgrade -y

# 3. Docker installieren
apt install -y docker.io docker-compose git curl

# 4. Docker starten
systemctl start docker
systemctl enable docker

# 5. Firewall konfigurieren
ufw allow 22/tcp      # SSH
ufw allow 8501/tcp    # Streamlit
ufw enable
```

### Projekt deployen

```bash
# 1. Projekt-Verzeichnis erstellen
mkdir -p /opt/skuld
cd /opt/skuld

# 2. Repository klonen
git clone https://github.com/Wuuzzaa/Skuld.git .
git checkout docker

# 3. Persistente Verzeichnisse erstellen
mkdir -p db logs

# 4. Container starten
docker-compose up -d --build

# 5. Logs prüfen
docker-compose logs -f
```

### Zugriff testen
Browser: **http://YOUR_SERVER_IP:8501**

---

## 3. Automatische Datensammlung

### Zeitplan (Cronjob)

Der Container sammelt automatisch Daten:
- **10:00 CET** (09:00 UTC) - Vormittags
- **16:00 CET** (15:00 UTC) - Nachmittags
- **Nur Werktags** (Montag-Freitag)

### Cronjob prüfen

```bash
# Cronjobs anzeigen
docker-compose exec skuld-app crontab -l

# Cron Service Status
docker-compose exec skuld-app service cron status

# Cron Logs live anzeigen
tail -f cron.log
```

### Manuell ausführen

```bash
# Sofort Datensammlung starten
docker-compose exec skuld-app python /app/Skuld/main.py

# Mit Logs
docker-compose exec skuld-app bash -c "cd /app/Skuld && python main.py"
```

---

## 4. Persistente Daten

Alle Daten werden auf dem Host gespeichert:

```
/opt/skuld/
├── db/
│   └── financial_data.db    # SQLite Datenbank (ca. 50-200 MB)
├── logs/
│   └── log.log               # Streamlit & App Logs
└── cron.log                  # Datensammlung Logs
```

### Datenbank Backup

```bash
# Manuelles Backup
cp /opt/skuld/db/financial_data.db \
   /opt/skuld/backups/financial_data_$(date +%Y%m%d).db

# Automatisches Backup Script erstellen
cat > /opt/skuld/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/skuld-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp /opt/skuld/db/financial_data.db $BACKUP_DIR/financial_data_${DATE}.db
# Alte Backups löschen (älter als 30 Tage)
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
echo "Backup completed: financial_data_${DATE}.db"
EOF

chmod +x /opt/skuld/backup.sh

# Cronjob für tägliches Backup (23:00 Uhr)
crontab -e
# Füge hinzu:
0 23 * * * /opt/skuld/backup.sh >> /opt/skuld/backup.log 2>&1
```

---

## 5. Updates deployen

```bash
cd /opt/skuld

# 1. Code aktualisieren
git pull origin docker

# 2. Container neu bauen und starten
docker-compose down
docker-compose up -d --build

# 3. Logs prüfen
docker-compose logs -f

# 4. Alte Images aufräumen
docker system prune -a -f
```

---

## 6. Monitoring & Wartung

### Container überwachen

```bash
# Container Status
docker ps

# Ressourcen-Nutzung
docker stats skuld-streamlit

# Disk Space prüfen
df -h
du -sh /opt/skuld/db/

# Logs Größe prüfen
ls -lh /opt/skuld/logs/
ls -lh /opt/skuld/cron.log
```

### Log Rotation

Docker rotiert Logs automatisch, aber für cron.log:

```bash
# Log Rotation konfigurieren
cat > /etc/logrotate.d/skuld << 'EOF'
/opt/skuld/cron.log {
    weekly
    rotate 4
    compress
    missingok
    notifempty
}
EOF
```

---

## 7. Production Setup mit SSL (Optional)

### Nginx Reverse Proxy

```bash
# Nginx installieren
apt install -y nginx certbot python3-certbot-nginx

# Nginx Config erstellen
cat > /etc/nginx/sites-available/skuld << 'EOF'
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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Aktivieren
ln -s /etc/nginx/sites-available/skuld /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Firewall anpassen
ufw allow 80/tcp
ufw allow 443/tcp

# SSL Zertifikat (kostenlos)
certbot --nginx -d your-domain.com
```

### docker-compose.yml anpassen

```yaml
# Port nur noch intern
ports:
  - "127.0.0.1:8501:8501"  # Nur localhost, nicht public
```

Dann: `docker-compose up -d`

---

## 8. Troubleshooting

### Container startet nicht

```bash
# Detaillierte Logs
docker-compose logs skuld-app

# Container Status
docker ps -a

# Neustart erzwingen
docker-compose down -v
docker-compose up -d --build
```

### Datenbank nicht gefunden

```bash
# Datenbank existiert?
ls -lh /opt/skuld/db/

# Permissions prüfen
docker-compose exec skuld-app ls -la /app/Skuld/db/

# Manuell erstellen
docker-compose exec skuld-app python /app/Skuld/main.py
```

### Cronjob läuft nicht

```bash
# In Container prüfen
docker-compose exec skuld-app bash

# Cron Status
service cron status

# Cronjobs anzeigen
crontab -l

# Logs prüfen
tail -f /var/log/cron.log
exit

# Auf Host
tail -f /opt/skuld/cron.log
```

### Streamlit lädt nicht

```bash
# Container läuft?
docker ps | grep skuld

# Port erreichbar?
curl http://localhost:8501

# Firewall?
ufw status

# Logs prüfen
docker-compose logs -f
```

### Speicherplatz voll

```bash
# Alte Docker Images löschen
docker system prune -a -f

# Alte Logs löschen
truncate -s 0 /opt/skuld/logs/log.log
truncate -s 0 /opt/skuld/cron.log

# Alte Backups löschen
find /opt/skuld-backups -name "*.db" -mtime +30 -delete
```

---

## 9. Sicherheit

### Best Practices

```bash
# SSH Key-only Auth
nano /etc/ssh/sshd_config
# PasswordAuthentication no
systemctl restart sshd

# Firewall Regeln minimieren
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Automatische Updates
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades

# Fail2ban für SSH Protection
apt install -y fail2ban
systemctl enable fail2ban
```

---

## 10. Zusammenfassung

### Was du brauchst:
✅ Hetzner Server (oder beliebiger Linux Server)  
✅ Docker & Docker Compose  
✅ Git  
✅ Port 8501 offen (oder Nginx für SSL)

### Was du NICHT brauchst:
❌ Google Drive API  
❌ Service Account Secrets  
❌ GitHub Actions  
❌ Externe Datenbank  

### Deployment in 3 Befehlen:
```bash
git clone https://github.com/Wuuzzaa/Skuld.git && cd Skuld
git checkout docker
docker-compose up -d --build
```

**🎉 Fertig! Die App läuft und sammelt automatisch 2x täglich Daten!**

