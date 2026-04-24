# Deployment Contract

Verbindliche Regeln für alle Skuld-Server. Jeder neue Server MUSS diesen Vertrag erfüllen,  
bevor ein Deployment-Workflow darauf zeigen darf.

---

## 1. Server-Vertrag (alle Umgebungen)

| Regel | Wert |
|-------|------|
| **CI/CD User** | `deploy` |
| **SSH Auth** | Key-only (kein Passwort) |
| **Sudo** | `NOPASSWD:ALL` via `/etc/sudoers.d/deploy-nopasswd` |
| **Docker-Gruppe** | `deploy` ist Mitglied von `docker` |
| **App-Verzeichnis** | `/opt/skuld/` (Owner: `deploy`) |
| **Docker-Netzwerke** | `web` (Traefik), `postgres_setup_default` (DB) |
| **Compose-Projekt** | `docker compose` in `/opt/skuld/` |
| **Logs** | `/opt/skuld/logs/` |
| **Backups** | `~/backups/postgres/` (Home von `deploy`) |
| **Firewall** | UFW aktiv, Docker `"iptables": false` |
| **SSH Härtung** | `PermitRootLogin no`, `PasswordAuthentication no`, `MaxAuthTries 2` |

## 2. Admin User (optional)

| Regel | Wert |
|-------|------|
| **Admin User** | `holu` (nur bei Hetzner Cloud-Init) |
| **Zweck** | Manueller Server-Zugang, Debugging |
| **Sudo** | `NOPASSWD:ALL` |
| **Nicht für CI/CD** | Workflows dürfen NUR `deploy` verwenden |

## 3. GitHub Environments

Jeder Server bekommt ein eigenes **GitHub Environment** mit diesen Secrets/Variables:

### Secrets (pro Environment)

| Secret | Beschreibung |
|--------|-------------|
| `DEPLOY_SSH_KEY` | SSH Private Key für den `deploy` User |
| `DEPLOY_USER` | Immer `deploy` |
| `DEPLOY_HOST` | IP oder Hostname des Servers |
| `POSTGRES_PASSWORD` | PostgreSQL Passwort |
| `AUTHELIA_JWT_SECRET` | Authelia JWT Secret |
| `AUTHELIA_SESSION_SECRET` | Authelia Session Secret |
| `AUTHELIA_STORAGE_ENCRYPTION_KEY` | Authelia Storage Key |
| `AUTHELIA_PASSWORD_HASH` | Argon2 Hash für Authelia Admin |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID (kann pro Env anders sein) |
| `MASSIVE_API_KEY` | MAssive API Key |
| `MASSIVE_API_KEY_FLAT_FILES` | MAssive Flat Files Key |

### Variables (pro Environment)

| Variable | Prod-Beispiel | Dev-Beispiel |
|----------|--------------|-------------|
| `DOMAIN_NAME` | `app.skuld-options.com` | `dev.skuld-options.com` |
| `AUTH_DOMAIN` | `auth.skuld-options.com` | `auth-dev.skuld-options.com` |
| `TRAEFIK_ENTRYPOINT` | `websecure` | `websecure` |
| `TRAEFIK_CERTRESOLVER_LABEL_SKULD` | `traefik.http.routers.skuld.tls.certresolver=letsencrypt` | `traefik.http.routers.skuld.tls.certresolver=letsencrypt` |
| `TRAEFIK_CERTRESOLVER_LABEL_AUTHELIA` | `traefik.http.routers.authelia.tls.certresolver=letsencrypt` | `traefik.http.routers.authelia.tls.certresolver=letsencrypt` |
| `AUTH_SCHEME` | `https` | `https` |
| `POSTGRES_HOST` | `postgres_setup-db-1` | `postgres_setup-db-1` |
| `POSTGRES_DB` | `Skuld` | `Skuld` |
| `POSTGRES_USER` | `admin` | `admin` |
| `POSTGRES_PORT` | `5432` | `5432` |

## 4. Aktuelle Environments

| GitHub Environment | Server | IP | Zweck |
|-------------------|--------|-----|-------|
| *(repo-level)* | Helsinki / SKULD-2 | `204.168.128.55` | Production |
| `dev-hetzner` | Falkenstein / Skuld-dev | `91.98.156.116` | Development |
| `skuld-1` | (alter Prod-Server) | – | Trigger-Jobs/Restore Source |
| `skuld-2` | Helsinki | `204.168.128.55` | Trigger-Jobs/Restore Target |
| *(self-hosted)* | Home Server | lokal | Staging (Testsystem) |

## 5. Checkliste: Neuen Server einrichten

1. **Server provisionieren** mit `ops/provision-hetzner.ps1` (nutzt Cloud-Init Template)
2. **SSH testen**: `ssh deploy@<IP>` → muss ohne Passwort funktionieren
3. **Sudo testen**: `sudo docker ps` → muss ohne Passwort funktionieren
4. **GitHub Environment anlegen** mit allen Secrets/Variables aus Abschnitt 3
5. **Docker-Netzwerke prüfen**: `docker network ls` → `web` und `postgres_setup_default`
6. **Traefik installieren** (falls der Server eigenes Traefik braucht)
7. **PostgreSQL-Stack deployen** (falls der Server eigene DB braucht)
8. **Deployment testen**: Workflow manuell triggern

## 6. Helsinki Migration

Helsinki wurde VOR diesem Contract eingerichtet. Einmaliger Fix nötig:

```bash
# Auf Helsinki einloggen
ssh deploy@204.168.128.55

# Option A: Script ausführen (erfordert einmalig das alte Passwort)
bash /opt/skuld/ops/fix-helsinki-sudoers.sh

# Option B: Manuell
echo '<DEPLOY_PASSWORD>' | sudo -S bash -c '
cat > /etc/sudoers.d/deploy-nopasswd << EOF
deploy ALL=(ALL) NOPASSWD:ALL
EOF
chmod 440 /etc/sudoers.d/deploy-nopasswd'

# Validierung
sudo -n docker ps   # Muss OHNE Passwort funktionieren
```

Nach der Migration kann das GitHub Secret `DEPLOY_PASSWORD` entfernt werden.
