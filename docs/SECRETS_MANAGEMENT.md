# 🔐 Sichere Secrets-Verwaltung für Production

## Problem
- Secrets sollten NICHT in Git committed werden
- Secrets sollten NICHT im Docker Image eingebacken sein
- Secrets sollten sicher auf dem Server gespeichert werden

## ✅ Empfohlene Lösung: Kombinierter Ansatz

### 1. Secrets außerhalb des Repository-Verzeichnisses speichern

```bash
# Auf dem Server
mkdir -p /etc/skuld/secrets
chmod 700 /etc/skuld/secrets  # Nur root kann lesen

# Secrets ablegen
nano /etc/skuld/secrets/service_account.json
nano /etc/skuld/secrets/secrets.toml

# Permissions setzen
chmod 600 /etc/skuld/secrets/*
```

### 2. Docker-Compose anpassen für externe Secrets

```yaml
# docker-compose.yml
version: '3.8'

services:
  skuld-app:
    build: .
    container_name: skuld-streamlit
    ports:
      - "8501:8501"
    volumes:
      - ./Skuld/db:/app/Skuld/db
      - ./Skuld/logs:/app/Skuld/logs
      # Secrets von außerhalb des Repos mounten
      - /etc/skuld/secrets/service_account.json:/app/service_account.json:ro
      - /etc/skuld/secrets/secrets.toml:/app/Skuld/.streamlit/secrets.toml:ro
    environment:
      - PYTHONUNBUFFERED=1
      - TZ=Europe/Berlin
    restart: unless-stopped
```

### 3. Deployment-Script erstellen

```bash
#!/bin/bash
# /opt/skuld/deploy.sh

set -e  # Bei Fehler abbrechen

echo "🚀 Deploying SKULD..."

# Zu Projekt-Verzeichnis wechseln
cd /opt/skuld

# Code aktualisieren
echo "📥 Pulling latest code..."
git pull origin master

# Secrets prüfen
if [ ! -f "/etc/skuld/secrets/service_account.json" ]; then
    echo "❌ ERROR: service_account.json not found!"
    exit 1
fi

# Container neu bauen
echo "🐳 Building containers..."
docker-compose down
docker-compose up -d --build

# Status prüfen
echo "✅ Deployment complete!"
docker-compose ps
```

## 🎯 Alternative Lösungen

### Option A: Environment Variables (für kleine Secrets)

```yaml
# docker-compose.yml
services:
  skuld-app:
    environment:
      - GOOGLE_PROJECT_ID=${GOOGLE_PROJECT_ID}
      - GOOGLE_PRIVATE_KEY=${GOOGLE_PRIVATE_KEY}
    env_file:
      - /etc/skuld/secrets/.env
```

```bash
# /etc/skuld/secrets/.env
GOOGLE_PROJECT_ID=your-project-id
GOOGLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n..."
```

### Option B: Docker Secrets (nur mit Docker Swarm)

```bash
# Docker Swarm initialisieren
docker swarm init

# Secrets erstellen
docker secret create service_account /etc/skuld/secrets/service_account.json

# docker-compose.yml
version: '3.8'
services:
  skuld-app:
    secrets:
      - service_account
secrets:
  service_account:
    external: true
```

### Option C: HashiCorp Vault (Enterprise-Level)

Für große Projekte mit vielen Secrets:
- Zentrale Secrets-Verwaltung
- Automatische Rotation
- Audit-Logs
- (Überdimensioniert für dein Projekt)

## 📋 Setup-Anleitung für Production

### Schritt 1: Secrets auf Server kopieren (einmalig)

```bash
# Von deinem lokalen PC aus
scp service_account.json root@YOUR_SERVER_IP:/tmp/

# Auf dem Server
ssh root@YOUR_SERVER_IP
mkdir -p /etc/skuld/secrets
mv /tmp/service_account.json /etc/skuld/secrets/
chmod 700 /etc/skuld/secrets
chmod 600 /etc/skuld/secrets/service_account.json

# Optional: secrets.toml erstellen
cat > /etc/skuld/secrets/secrets.toml << 'EOF'
# Streamlit Secrets
[connections.gcs]
type = "service_account"
project_id = "your-project-id"
EOF
chmod 600 /etc/skuld/secrets/secrets.toml
```

### Schritt 2: docker-compose.yml aktualisieren

Siehe oben - Volumes auf `/etc/skuld/secrets/` zeigen lassen

### Schritt 3: Deployment testen

```bash
cd /opt/skuld
docker-compose down
docker-compose up -d --build
docker-compose logs -f
```

## 🛡️ Sicherheits-Best Practices

### 1. Dateiberechtigungen
```bash
# Nur root kann secrets lesen
chmod 700 /etc/skuld/secrets
chmod 600 /etc/skuld/secrets/*
chown root:root /etc/skuld/secrets/*
```

### 2. Secrets nicht im Repository
```bash
# .gitignore bereits konfiguriert
service_account.json
.streamlit/secrets.toml
*.env
```

### 3. Backup (verschlüsselt)
```bash
# Mit GPG verschlüsseln
tar czf - /etc/skuld/secrets | gpg --encrypt --recipient your@email.com > secrets_backup.tar.gz.gpg

# Wiederherstellen
gpg --decrypt secrets_backup.tar.gz.gpg | tar xzf -
```

### 4. Zugriff einschränken
```bash
# Nicht-root User erstellen
adduser skuld-app --disabled-password
usermod -aG docker skuld-app

# ACL für Secrets-Zugriff
setfacl -m u:skuld-app:r /etc/skuld/secrets/service_account.json
```

### 5. SSH Key statt Passwort
```bash
# SSH Key-based Auth erzwingen
nano /etc/ssh/sshd_config
# PasswordAuthentication no
# PubkeyAuthentication yes
systemctl restart sshd
```

### 6. Firewall konfigurieren
```bash
# Nur notwendige Ports öffnen
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (wenn Nginx)
ufw allow 443/tcp   # HTTPS
ufw allow 8501/tcp  # Streamlit (nur wenn direkt exposed)
ufw enable
```

## 🔄 GitHub Actions mit Secrets

### Secrets NICHT direkt deployen

```yaml
# .github/workflows/deploy.yml
- name: Deploy to server
  run: |
    # NUR Code deployen, keine Secrets
    git pull origin master
    docker-compose up -d --build
```

### Secrets manuell verwalten

Secrets bleiben auf dem Server in `/etc/skuld/secrets/` und werden nicht durch GitHub Actions überschrieben.

## ⚠️ Was NICHT tun

❌ Secrets in Git committen (auch nicht in private Repos)
❌ Secrets im Dockerfile hardcoden
❌ Secrets in Docker Image einbacken
❌ Secrets in öffentlichen Logs ausgeben
❌ Secrets als unverschlüsselte Umgebungsvariablen in GitHub Actions
❌ Secrets per HTTP übertragen (nur HTTPS/SSH)

## ✅ Checkliste

- [ ] Secrets in `/etc/skuld/secrets/` mit chmod 600
- [ ] docker-compose.yml verwendet externe Volume Mounts
- [ ] .gitignore schließt alle Secret-Dateien aus
- [ ] Firewall ist aktiviert
- [ ] SSH Key-Auth ist konfiguriert
- [ ] Nur notwendige Ports sind offen
- [ ] Regelmäßige verschlüsselte Backups
- [ ] Secrets niemals in Logs ausgeben

## 📞 Notfall-Plan

### Secrets kompromittiert?

1. **Sofort widerrufen**: Google Cloud Console → Service Account löschen
2. **Neue Secrets generieren**: Neuen Service Account erstellen
3. **Server aktualisieren**: Neue Secrets nach `/etc/skuld/secrets/` kopieren
4. **Container neu starten**: `docker-compose restart`
5. **Logs prüfen**: Auf verdächtige Aktivitäten checken
6. **Root-Cause finden**: Wie wurden Secrets kompromittiert?
