# Deployment auf Hetzner Server

## 1. Server Vorbereitung (einmalig)

### SSH zum Server verbinden
```bash
ssh root@YOUR_SERVER_IP
```

### Docker installieren
```bash
# System aktualisieren
apt update && apt upgrade -y

# Docker installieren
apt install -y docker.io docker-compose

# Docker starten und autostart aktivieren
systemctl start docker
systemctl enable docker

# Git installieren (falls nicht vorhanden)
apt install -y git

# Optional: Nicht-root User erstellen
adduser skuld
usermod -aG docker skuld
```

### Projekt-Verzeichnis erstellen
```bash
mkdir -p /opt/skuld
cd /opt/skuld
```

### Repository klonen
```bash
git clone https://github.com/Wuuzzaa/Skuld.git .
git checkout clean-up-data-collection
```

### Secrets auf Server kopieren (von deinem lokalen PC aus)
```powershell
# service_account.json hochladen
scp C:\Python\SKULD\service_account.json root@YOUR_SERVER_IP:/opt/skuld/

# Wenn du später secrets.toml brauchst (optional):
# scp C:\Python\SKULD\.streamlit\secrets.toml root@YOUR_SERVER_IP:/opt/skuld/.streamlit/
```

### Firewall konfigurieren
```bash
# Port 8501 für Streamlit öffnen
ufw allow 8501/tcp
ufw allow 22/tcp  # SSH nicht vergessen!
ufw enable
```

## 2. App starten auf dem Server

```bash
cd /opt/skuld

# Container bauen und starten
docker-compose up -d --build

# Logs prüfen
docker-compose logs -f
```

## 3. Zugriff testen

Öffne im Browser: `http://YOUR_SERVER_IP:8501`

## 4. Container verwalten

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
```

## 5. Auto-Deployment mit GitHub Actions

Die Workflow-Datei `.github/workflows/deploy.yml` ist bereits erstellt.

### GitHub Secrets einrichten:

1. Gehe zu: https://github.com/Wuuzzaa/Skuld/settings/secrets/actions
2. Füge folgende Secrets hinzu:

   - `HETZNER_HOST`: Deine Server IP
   - `HETZNER_USER`: `root` (oder dein erstellter User)
   - `HETZNER_SSH_KEY`: Dein privater SSH Key (kompletten Inhalt)
   - `HETZNER_PORT`: `22` (Standard SSH Port)

### SSH Key für GitHub Actions erstellen:

```bash
# Auf deinem lokalen PC oder direkt auf dem Server:
ssh-keygen -t ed25519 -C "github-actions-skuld" -f skuld_deploy_key

# Public Key zum Server hinzufügen
cat skuld_deploy_key.pub >> ~/.ssh/authorized_keys

# Private Key in GitHub Secrets einfügen (HETZNER_SSH_KEY)
cat skuld_deploy_key
```

### Auto-Deployment testen:

```bash
# Lokale Änderung machen
git add .
git commit -m "Test deployment"
git push origin clean-up-data-collection

# Oder für Production:
git push origin master
```

GitHub Actions wird automatisch:
1. SSH zum Server verbinden
2. Code pullen
3. Container neu bauen
4. Container starten
5. Alte Images aufräumen

## 6. Production-Setup (Optional)

### Reverse Proxy mit Nginx + SSL

```bash
apt install -y nginx certbot python3-certbot-nginx

# Nginx konfigurieren
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
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}

# Aktivieren
ln -s /etc/nginx/sites-available/skuld /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# SSL Zertifikat (kostenlos)
certbot --nginx -d your-domain.com
```

### Container Monitoring

```bash
# Docker Stats anzeigen
docker stats skuld-streamlit

# Disk Space prüfen
df -h

# Logs rotieren (docker-compose.yml bereits konfiguriert)
```

## Troubleshooting

### Container startet nicht
```bash
docker-compose logs -f
docker-compose down -v
docker-compose up -d --build
```

### Port bereits belegt
```bash
lsof -i :8501
# Prozess beenden oder Port in docker-compose.yml ändern
```

### Kein Speicherplatz mehr
```bash
# Alte Docker Images löschen
docker system prune -a

# Logs löschen
docker-compose down
rm -rf Skuld/logs/*
docker-compose up -d
```

### Datenbank-Fehler
```bash
# Datenbank neu downloaden
docker-compose exec skuld-streamlit rm -f /app/Skuld/db/financial_data.db
docker-compose restart
```
